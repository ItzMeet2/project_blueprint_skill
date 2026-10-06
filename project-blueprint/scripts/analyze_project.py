#!/usr/bin/env python3
"""Deterministic first-pass scan of a project folder.

Usage: analyze_project.py <project_path> --out <dir> [--max-files 2000]

Walks the tree, detects languages and stack from file names and extensions,
guesses key directories and entry points, and writes <out>/analysis.raw.json.
The agent merges and corrects that file into blueprint/profile.json.

Lightweight regex extractors then add "routes", "screens" and "entities"
(every item marked "inferred": true). A failing extractor or unreadable file is
logged to "warnings" and never stops the scan.

Safety: standard library only, no network, never executes analyzed code, and
never opens secret files (.env, *.pem, *.key, secrets*); their names are listed
under "sensitive_files_present". Only non-secret files under 1 MB are read.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from collections import Counter

MAX_FILE_BYTES = 1024 * 1024
MAX_KEY_DIR_DEPTH = 3
MAX_LIST_ITEMS = 200  # caps output size for the listed (non-count) sections

SKIP_DIRS = {
    ".git", "node_modules", "bin", "obj", "venv", ".venv",
    "dist", "build", ".next", "Library", "Temp",
}

LANGUAGES = {
    ".cs": "C#", ".cshtml": "Razor", ".razor": "Razor", ".vb": "Visual Basic",
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin",
    ".dart": "Dart", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sql": "SQL",
    ".sh": "Shell", ".ps1": "PowerShell",
}

# marker file name or glob -> (technology, ecosystem note)
STACK_MARKERS = [
    ("*.csproj", ".NET project"),
    ("*.sln", ".NET solution"),
    ("package.json", "Node.js / npm"),
    ("requirements.txt", "Python (pip)"),
    ("pyproject.toml", "Python (pyproject)"),
    ("pubspec.yaml", "Flutter / Dart"),
    ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java/Kotlin (Gradle)"),
    ("build.gradle.kts", "Java/Kotlin (Gradle)"),
    ("Cargo.toml", "Rust (Cargo)"),
    ("go.mod", "Go modules"),
    ("Dockerfile", "Docker"),
    ("docker-compose.yml", "Docker Compose"),
    ("docker-compose.yaml", "Docker Compose"),
]
STACK_MARKER_DIRS = [("ProjectSettings", "Unity")]

DIR_ROLES = {
    "controllers": "HTTP controllers",
    "views": "UI views / templates",
    "models": "Data models / entities",
    "data": "Data access (DbContext, repositories)",
    "wwwroot": "Static web assets",
    "src": "Application source",
    "tests": "Automated tests",
    "test": "Automated tests",
    "services": "Business logic services",
    "migrations": "Database migrations",
    "components": "UI components",
    "pages": "Page routes / views",
    "app": "Application root / routes",
    "routes": "Route definitions",
    "api": "API endpoints",
    "public": "Static assets",
    "assets": "Static assets",
    "docs": "Documentation",
    "scripts": "Helper scripts",
    "config": "Configuration",
    "lib": "Library code",
    "properties": "Project properties",
}

ENTRY_POINT_NAMES = {
    "Program.cs", "Startup.cs", "main.py", "app.py", "manage.py", "wsgi.py",
    "asgi.py", "index.js", "server.js", "app.js", "main.js", "index.ts",
    "main.ts", "main.go", "main.dart", "Main.java", "Application.java",
    "MainActivity.kt", "main.rs", "lib.rs",
}


def is_sensitive(name):
    """True for files that must never be read (secrets, keys, env files)."""
    lower = name.lower()
    return (
        lower == ".env"
        or lower.startswith(".env.")
        or lower.endswith((".pem", ".key"))
        or lower.startswith("secrets")
    )


def load_gitignore(root):
    """Parse root .gitignore into simple patterns.

    Limitation: only the root .gitignore is read, and only basic patterns are
    supported (names, globs like *.log, trailing-slash directories, leading-slash
    anchors). Negation (!) and nested .gitignore files are ignored.
    """
    path = os.path.join(root, ".gitignore")
    patterns = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                patterns.append(line)
    except OSError:
        pass
    return patterns


def ignored_by_gitignore(rel_path, is_dir, patterns):
    name = rel_path.rsplit("/", 1)[-1]
    for pat in patterns:
        dir_only = pat.endswith("/")
        pat = pat.rstrip("/")
        if dir_only and not is_dir:
            continue
        if pat.startswith("/"):
            if fnmatch.fnmatch(rel_path, pat.lstrip("/")):
                return True
        elif "/" in pat:
            if fnmatch.fnmatch(rel_path, pat):
                return True
        elif fnmatch.fnmatch(name, pat):
            return True
    return False


def scan(root, max_files):
    patterns = load_gitignore(root)
    ext_counts = Counter()
    lang_counts = Counter()
    stack = []
    key_dirs = []
    entry_points = []
    sensitive = []
    files = []  # relative paths of scanned (non-secret, <=1 MB) files
    total = 0
    skipped_large = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir

        kept = []
        for d in sorted(dirnames):
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if d in SKIP_DIRS or ignored_by_gitignore(rel, True, patterns):
                continue
            kept.append(d)
            depth = rel.count("/") + 1
            role = DIR_ROLES.get(d.lower())
            if role and depth <= MAX_KEY_DIR_DEPTH:
                key_dirs.append({"path": rel + "/", "role": role, "inferred": True})
            for marker, tech in STACK_MARKER_DIRS:
                if d == marker:
                    stack.append({"marker": rel + "/", "technology": tech})
        dirnames[:] = kept

        for fname in sorted(filenames):
            rel = f"{rel_dir}/{fname}" if rel_dir else fname
            if is_sensitive(fname):
                sensitive.append(rel)  # name only; never opened
                continue
            if ignored_by_gitignore(rel, False, patterns):
                continue
            if total >= max_files:
                truncated = True
                break
            try:
                size = os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                skipped_large += 1
                continue
            total += 1
            files.append(rel)
            ext = os.path.splitext(fname)[1].lower() or "(none)"
            ext_counts[ext] += 1
            if ext in LANGUAGES:
                lang_counts[LANGUAGES[ext]] += 1
            for marker, tech in STACK_MARKERS:
                if fnmatch.fnmatch(fname, marker):
                    stack.append({"marker": rel, "technology": tech})
                    break
            if fname in ENTRY_POINT_NAMES:
                entry_points.append(rel)
        if truncated:
            break

    return files, {
        "scanned_root": os.path.basename(os.path.abspath(root)),
        "file_stats": {
            "files_scanned": total,
            "skipped_large_files": skipped_large,
            "by_extension": dict(sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
        "languages": dict(sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "stack": stack[:MAX_LIST_ITEMS],
        "key_dirs": key_dirs[:MAX_LIST_ITEMS],
        "entry_points": entry_points[:MAX_LIST_ITEMS],
        "sensitive_files_present": sensitive[:MAX_LIST_ITEMS],
        "truncated": truncated,
    }


# --------------------------------------------------------------------------
# Extractors: lightweight regex heuristics, not parsers. Each one is a
# separate function taking (root, files, warnings) and returning a dict with
# any of the keys "routes", "screens", "entities".
# --------------------------------------------------------------------------

MAX_EXTRACTED = 500
HTTP_VERBS = ("get", "post", "put", "delete", "patch", "head", "options")


def read_text(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def collect(root, files, select, parse, warnings, label):
    """Run parse(text, rel) on every selected file; a bad file only adds a warning."""
    items = []
    for rel in files:
        if not select(rel):
            continue
        try:
            items.extend(parse(read_text(root, rel), rel))
        except Exception as exc:  # noqa: BLE001 - extractors must never crash the scan
            warnings.append(f"{label}: {rel}: {type(exc).__name__}: {exc}")
    return items


def kebab(text):
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", text)
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def words(text):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).replace("_", " ").replace("-", " ").strip()


def norm_path(path):
    path = "/" + path.strip().lstrip("~").strip("/")
    return re.sub(r"/{2,}", "/", path)


def has_ext(rel, *exts):
    return rel.lower().endswith(exts)


def in_dir(rel, *names):
    parts = rel.lower().split("/")[:-1]
    return any(n in parts for n in names)


def match_brace(text, open_idx):
    """Index just past the brace that closes the one at open_idx (or len(text))."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


# ---- ASP.NET -------------------------------------------------------------

CS_CONTROLLER_RE = re.compile(r"\bclass\s+(\w+?)Controller\b")
CS_VERB_ATTR_RE = re.compile(
    r"\[\s*Http(Get|Post|Put|Delete|Patch|Head|Options)\s*(?:\(\s*(?:\"([^\"]*)\")?[^)\]]*\))?\s*\]")
CS_METHOD_RE = re.compile(
    r"public\s+(?:async\s+|virtual\s+)*[\w<>\.\?,\[\]]+\s+(\w+)\s*\(")
CS_MINIMAL_RE = re.compile(r"\.Map(Get|Post|Put|Delete|Patch)\(\s*\"([^\"]+)\"")


def aspnet_path(prefix, template, controller, action):
    if template is not None and template.startswith(("/", "~/")):
        return norm_path(template)
    if template:
        return norm_path(f"{prefix}/{template}" if prefix is not None else template)
    if prefix is not None:
        return norm_path(prefix)
    if controller.lower() == "home" and action.lower() == "index":
        return "/"
    return norm_path(f"{controller}/{action}".lower())


def parse_aspnet_controller(text, rel):
    routes = []
    for cm in CS_CONTROLLER_RE.finditer(text):
        controller = cm.group(1)
        head = text[:cm.start()]
        attrs = head[max(head.rfind("}"), head.rfind(";")) + 1:]
        rm = re.search(r"\[\s*Route\(\s*\"([^\"]*)\"", attrs)
        prefix = rm.group(1).replace("[controller]", controller.lower()) if rm else None
        body_start = cm.end()
        brace = text.find("{", body_start)
        body = text[body_start:match_brace(text, brace)] if brace != -1 else text[body_start:]
        for am in CS_VERB_ATTR_RE.finditer(body):
            mm = CS_METHOD_RE.search(body, am.end())
            if not mm:
                continue
            action = mm.group(1)
            routes.append({
                "method": am.group(1).upper(),
                "path": aspnet_path(prefix, am.group(2), controller, action),
                "handler": f"{controller}Controller.{action}",
                "inferred": True,
            })
    for mm in CS_MINIMAL_RE.finditer(text):
        routes.append({"method": mm.group(1).upper(), "path": norm_path(mm.group(2)),
                       "handler": rel, "inferred": True})
    return routes


def extract_aspnet_routes(root, files, warnings):
    routes = collect(root, files, lambda r: has_ext(r, ".cs"),
                     parse_aspnet_controller, warnings, "aspnet-routes")
    return {"routes": routes}


def extract_razor_views(root, files, warnings):
    screens = []
    for rel in files:
        parts = rel.split("/")
        if "Views" not in parts or not rel.lower().endswith(".cshtml"):
            continue
        sub = parts[parts.index("Views") + 1:]
        if len(sub) != 2:
            continue
        folder, view = sub[0], os.path.splitext(sub[1])[0]
        is_layout = view.startswith("_")
        view_name = view.lstrip("_")
        name = words(folder) if view_name == "Index" else f"{words(folder)} {words(view_name)}"
        screen = {"id": kebab(f"{folder}-{view_name}"), "name": name,
                  "source": rel, "inferred": True}
        if is_layout:
            screen["is_layout"] = True  # layouts/partials are not real screens; drop when merging
        screens.append(screen)
    return {"screens": screens}


# ---- Express / Fastify ---------------------------------------------------

JS_ROUTE_RE = re.compile(
    r"\b(?:app|router|fastify|server|api|routes?|\w*[Rr]outer)\.(get|post|put|delete|patch)"
    r"\(\s*[\"'`](/[^\"'`]*)[\"'`]")


def parse_js_routes(text, rel):
    return [{"method": m.group(1).upper(), "path": norm_path(m.group(2)),
             "handler": rel, "inferred": True} for m in JS_ROUTE_RE.finditer(text)]


def extract_js_routes(root, files, warnings):
    routes = collect(
        root, files,
        lambda r: has_ext(r, ".js", ".mjs", ".cjs", ".ts") and not in_dir(r, "test", "tests", "__tests__"),
        parse_js_routes, warnings, "express")
    return {"routes": routes}


# ---- Flask / FastAPI -----------------------------------------------------

PY_FLASK_RE = re.compile(r"@\s*\w+\.route\(\s*[\"'](/[^\"']*)[\"']([^)]*)\)")
PY_FASTAPI_RE = re.compile(r"@\s*(\w+)\.(get|post|put|delete|patch)\(\s*[\"'](/[^\"']*)[\"']")
PY_DEF_RE = re.compile(r"def\s+(\w+)\s*\(")
PY_DECORATOR_NOISE = {"mock", "patch", "pytest", "unittest"}


def parse_python_routes(text, rel):
    routes = []
    for m in PY_FLASK_RE.finditer(text):
        methods = re.findall(r"[\"'](\w+)[\"']", m.group(2).split("methods", 1)[1]) \
            if "methods" in m.group(2) else ["GET"]
        d = PY_DEF_RE.search(text, m.end())
        for method in methods:
            routes.append({"method": method.upper(), "path": norm_path(m.group(1)),
                           "handler": d.group(1) if d else rel, "inferred": True})
    for m in PY_FASTAPI_RE.finditer(text):
        if m.group(1) in PY_DECORATOR_NOISE:
            continue
        d = PY_DEF_RE.search(text, m.end())
        routes.append({"method": m.group(2).upper(), "path": norm_path(m.group(3)),
                       "handler": d.group(1) if d else rel, "inferred": True})
    return routes


def extract_python_routes(root, files, warnings):
    routes = collect(root, files,
                     lambda r: has_ext(r, ".py") and not in_dir(r, "test", "tests"),
                     parse_python_routes, warnings, "flask-fastapi")
    return {"routes": routes}


# ---- Next.js -------------------------------------------------------------

NEXT_APP_RE = re.compile(r"^(?:src/)?app/(?:(.*)/)?(page|route)\.(?:js|jsx|ts|tsx)$")
NEXT_PAGES_RE = re.compile(r"^(?:src/)?pages/(.+)\.(?:js|jsx|ts|tsx)$")


def next_detected(root, files, warnings):
    for rel in files:
        if rel.endswith("package.json"):
            try:
                if re.search(r"\"next\"\s*:", read_text(root, rel)):
                    return True
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"nextjs: {rel}: {type(exc).__name__}: {exc}")
    return False


def extract_nextjs(root, files, warnings):
    if not next_detected(root, files, warnings):
        return {}
    routes, screens = [], []
    for rel in files:
        m = NEXT_APP_RE.match(rel)
        kind, route_dir = None, None
        if m:
            segs = [s for s in (m.group(1) or "").split("/")
                    if s and not s.startswith("(") and not s.startswith("@")]
            kind = "api" if m.group(2) == "route" else "page"
            route_dir = "/".join(segs)
        else:
            m = NEXT_PAGES_RE.match(rel)
            if m:
                segs = m.group(1).split("/")
                if segs[-1].startswith("_"):
                    continue
                if segs[-1] == "index":
                    segs = segs[:-1]
                route_dir = "/".join(segs)
                kind = "api" if segs[:1] == ["api"] else "page"
        if kind is None:
            continue
        path = norm_path(route_dir)
        if kind == "api":
            routes.append({"method": "ANY", "path": path, "handler": rel, "inferred": True})
        else:
            routes.append({"method": "GET", "path": path, "handler": rel, "inferred": True})
            sid = kebab(route_dir) or "home"
            last = route_dir.split("/")[-1] if route_dir else "Home"
            screens.append({"id": sid, "name": words(last.strip("[]")).title() or "Home",
                            "source": rel, "inferred": True})
    return {"routes": routes, "screens": screens}


# ---- Entities ------------------------------------------------------------

CS_CLASS_RE = re.compile(
    r"\bclass\s+(\w+)(?:\s*<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{")
CS_PROP_RE = re.compile(
    r"public\s+(?:virtual\s+|required\s+)*([\w\.\[\]]+(?:<[^>]+>)?\??)\s+(\w+)\s*\{\s*(?:get|init)")
CS_DBSET_RE = re.compile(r"DbSet<(\w+)>")


def parse_csharp_entities(text, rel):
    items = []
    in_models = in_dir(rel, "models", "entities")
    for m in CS_CLASS_RE.finditer(text):
        body = text[m.end() - 1:match_brace(text, m.end() - 1)]
        fields = [{"name": p.group(2), "type": p.group(1)} for p in CS_PROP_RE.finditer(body)]
        items.append({"_kind": "class", "name": m.group(1), "fields": fields,
                      "in_models": in_models})
    for m in CS_DBSET_RE.finditer(text):
        items.append({"_kind": "dbset", "name": m.group(1)})
    return items


TS_INTERFACE_RE = re.compile(r"interface\s+(\w+)(?:\s+extends\s+[\w,\s<>]+)?\s*\{([^}]*)\}")
TS_FIELD_RE = re.compile(r"^\s*(?:readonly\s+)?(\w+)\??\s*:\s*([^;,\n]+)", re.MULTILINE)


def parse_ts_entities(text, rel):
    items = []
    for m in TS_INTERFACE_RE.finditer(text):
        fields = [{"name": f.group(1), "type": f.group(2).strip()}
                  for f in TS_FIELD_RE.finditer(m.group(2))]
        items.append({"_kind": "class", "name": m.group(1), "fields": fields, "in_models": True})
    return items


PY_MODEL_CLASS_RE = re.compile(
    r"^(?:@dataclass[^\n]*\n)?class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", re.MULTILINE)
PY_MODEL_BASES = ("BaseModel", "Model", "Base", "SQLModel", "Document")


def parse_python_entities(text, rel):
    items = []
    for m in PY_MODEL_CLASS_RE.finditer(text):
        is_dataclass = m.group(0).startswith("@dataclass")
        bases = m.group(2) or ""
        if not is_dataclass and not any(b in bases for b in PY_MODEL_BASES):
            continue
        fields = []
        for line in text[m.end():].splitlines()[1:]:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            f = re.match(r"^\s{4}(\w+)\s*:\s*([^=#\n]+)", line)
            if f:
                fields.append({"name": f.group(1), "type": f.group(2).strip()})
        items.append({"_kind": "class", "name": m.group(1), "fields": fields, "in_models": True})
    return items


def extract_entities(root, files, warnings):
    items = []
    items += collect(root, files, lambda r: has_ext(r, ".cs"),
                     parse_csharp_entities, warnings, "entities-csharp")
    items += collect(root, files,
                     lambda r: has_ext(r, ".ts", ".tsx") and in_dir(r, "models", "types"),
                     parse_ts_entities, warnings, "entities-typescript")
    items += collect(root, files,
                     lambda r: has_ext(r, ".py") and (in_dir(r, "models") or r.endswith("models.py")),
                     parse_python_entities, warnings, "entities-python")
    classes = {}
    for it in items:
        if it["_kind"] == "class" and it["name"] not in classes:
            classes[it["name"]] = it
    wanted = [n for n, c in classes.items() if c["in_models"]]
    wanted += [it["name"] for it in items
               if it["_kind"] == "dbset" and it["name"] in classes and it["name"] not in wanted]
    entities = []
    for name in wanted:
        entity = {"name": name, "fields": classes[name]["fields"], "inferred": True}
        relations = []
        for f in entity["fields"]:
            fname = f["name"]
            if len(fname) > 2 and fname.endswith("Id") and fname[:-2] in wanted:
                relations.append({"to": fname[:-2], "kind": "*..1"})
        if relations:
            entity["relations"] = relations
        entities.append(entity)
    return {"entities": entities}


EXTRACTORS = [
    ("aspnet-routes", extract_aspnet_routes),
    ("razor-views", extract_razor_views),
    ("express", extract_js_routes),
    ("flask-fastapi", extract_python_routes),
    ("nextjs", extract_nextjs),
    ("entities", extract_entities),
]


def run_extractors(root, files):
    out = {"routes": [], "screens": [], "entities": []}
    warnings = []
    for name, fn in EXTRACTORS:
        try:
            found = fn(root, files, warnings)
        except Exception as exc:  # noqa: BLE001 - one broken extractor must not stop the others
            warnings.append(f"{name}: extractor failed: {type(exc).__name__}: {exc}")
            continue
        for key in out:
            out[key].extend(found.get(key, []))
    for key in out:
        if len(out[key]) > MAX_EXTRACTED:
            warnings.append(f"{key}: output capped at {MAX_EXTRACTED} items")
            out[key] = out[key][:MAX_EXTRACTED]
    seen = set()
    unique_screens = []
    for s in out["screens"]:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique_screens.append(s)
    out["screens"] = unique_screens
    out["warnings"] = warnings
    return out


def print_summary(result, out_path):
    print(f"Scanned: {result['scanned_root']} "
          f"({result['file_stats']['files_scanned']} files"
          f"{', truncated' if result['truncated'] else ''})")
    if result["languages"]:
        langs = ", ".join(f"{k} ({v})" for k, v in list(result["languages"].items())[:5])
        print(f"Languages: {langs}")
    if result["stack"]:
        markers = ", ".join(f"{s['technology']}" for s in result["stack"][:8])
        print(f"Stack markers: {markers}")
    if result["entry_points"]:
        print("Entry points: " + ", ".join(result["entry_points"][:5]))
    print(f"Extracted: {len(result['routes'])} routes, {len(result['screens'])} screens, "
          f"{len(result['entities'])} entities")
    if result["warnings"]:
        print(f"Warnings: {len(result['warnings'])} (see analysis.raw.json)")
    if result["sensitive_files_present"]:
        print(f"Sensitive files present (not read): {len(result['sensitive_files_present'])}")
    print(f"Wrote {out_path}")


def build_parser():
    p = argparse.ArgumentParser(
        description="Scan a project folder and write analysis.raw.json (no code is executed).")
    p.add_argument("project_path", help="Path to the project folder to analyze")
    p.add_argument("--out", required=True, help="Output directory for analysis.raw.json")
    p.add_argument("--max-files", type=int, default=2000,
                   help="Stop after this many files and mark the result truncated (default 2000)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.project_path):
        print(f"error: project path does not exist or is not a directory: {args.project_path}",
              file=sys.stderr)
        return 2
    if args.max_files < 1:
        print("error: --max-files must be at least 1", file=sys.stderr)
        return 2
    files, result = scan(args.project_path, args.max_files)
    result.update(run_extractors(args.project_path, files))
    try:
        os.makedirs(args.out, exist_ok=True)
        out_path = os.path.join(args.out, "analysis.raw.json")
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1
    print_summary(result, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
