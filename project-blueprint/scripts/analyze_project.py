#!/usr/bin/env python3
"""Deterministic first-pass scan of a project folder.

Usage: analyze_project.py <project_path> --out <dir> [--max-files 2000]

Walks the tree, detects languages and stack from file names and extensions,
guesses key directories and entry points, and writes <out>/analysis.raw.json.
The agent merges and corrects that file into blueprint/profile.json.

Safety: standard library only, no network, never executes analyzed code, and
never opens secret files (.env, *.pem, *.key, secrets*); their names are listed
under "sensitive_files_present". The core scan reads no file contents at all.
"""

import argparse
import fnmatch
import json
import os
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

    return {
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
    result = scan(args.project_path, args.max_files)
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
