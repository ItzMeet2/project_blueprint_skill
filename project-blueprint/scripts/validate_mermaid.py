#!/usr/bin/env python3
"""Heuristic validator for Mermaid diagrams in .md and .mmd files.

Usage: validate_mermaid.py <file-or-dir>

Scans ```mermaid fenced blocks in .md files and whole .mmd files. For each
diagram it checks: a known diagram type on the first line, a valid flowchart
direction, a non-empty body, balanced quotes and brackets, and (as warnings)
node ids redefined with different labels, unescaped < / > in flowchart labels
and a bare 'end' used as a node. If `mmdc` (mermaid-cli) is on PATH it is also
run for real parsing; otherwise only the heuristics run.

Output lines look like `path:line: ERROR message`. Exit code is 1 if any ERROR
was reported, 2 if the path does not exist, else 0. Standard library only, no
network access; files are only read, never executed.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

KNOWN_TYPES = {
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram-v2",
    "stateDiagram", "erDiagram", "gantt", "journey", "pie", "mindmap", "timeline",
    "gitGraph", "requirementDiagram", "quadrantChart", "sankey-beta", "xychart-beta",
    "block-beta", "packet-beta", "architecture-beta", "kanban", "C4Context",
    "C4Container", "C4Component", "C4Dynamic", "C4Deployment",
}
FLOW_DIRECTIONS = {"TB", "TD", "BT", "RL", "LR"}
# Free-text diagram types where quotes and brackets are legitimate in prose.
FREE_TEXT_TYPES = {"sequenceDiagram", "journey", "gantt", "timeline", "gitGraph"}
LINE_BRACKET_TYPES = {"flowchart", "graph", "mindmap"}
BLOCK_BRACE_TYPES = {"classDiagram", "erDiagram", "stateDiagram", "stateDiagram-v2"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
PAIRS = {")": "(", "]": "[", "}": "{"}
MMDC_TIMEOUT = 60

FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*mermaid\b")
ASYMMETRIC_RE = re.compile(r"\w+>[^\]\n]*\]")
ER_RELATION_RE = re.compile(
    r"(?:\|\||\|o|o\||\}o|o\{|\}\||\|\{)\s*(?:--|\.\.)\s*"
    r"(?:\|\||\|o|o\||\}o|o\{|\}\||\|\{)")
NODE_DEF_RE = re.compile(
    r"(?<![\w-])([A-Za-z_][\w-]*)(?:\[\[|\[\(|\(\(|\(\[|\[/|\[\\|\{\{|\[|\(|\{)"
    r"(?:\"([^\"]*)\"|([^\]\)\}\"]*))")
BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
BARE_END_RE = re.compile(r"(?:^|\s|-->|---|-\.->|==>)end(?:\s|$|\[|\()")


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0
        self.diagrams = 0
        self.files = 0

    def emit(self, path, line, level, message):
        if level == "ERROR":
            self.errors += 1
        elif level == "WARNING":
            self.warnings += 1
        print(f"{path}:{line}: {level} {message}")


def read_lines(path):
    """Read a file as text lines; never raises on bad encodings. Returns (lines, had_bad_bytes)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text, bad = raw.decode("utf-8-sig"), False
    except UnicodeDecodeError:
        text, bad = raw.decode("utf-8", errors="replace"), True
    return text.splitlines(), bad


def extract_blocks(lines, is_mmd):
    """Return (blocks, unterminated) where a block is (first_line_no, [lines])."""
    if is_mmd:
        return [(1, lines)], []
    blocks, unterminated = [], []
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence = m.group(1)
        start = i + 1
        j = start
        while j < len(lines) and not re.match(
                r"^\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$", lines[j]):
            j += 1
        if j >= len(lines):
            unterminated.append(i + 1)
        blocks.append((start + 1, lines[start:j]))
        i = j + 1
    return blocks, unterminated


def meaningful_lines(first_no, lines):
    """Yield (line_no, text) for diagram lines, skipping frontmatter, comments and blanks."""
    out = []
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].strip() == "---":
        idx += 1
        while idx < len(lines) and lines[idx].strip() != "---":
            idx += 1
        idx += 1
    for k in range(idx, len(lines)):
        text = lines[k].strip()
        if text and not text.startswith("%%"):
            out.append((first_no + k, lines[k]))
    return out


def strip_quoted(text):
    return re.sub(r"\"[^\"]*\"", '""', text)


def check_line_brackets(text):
    """Return an error message if brackets on one line do not balance, else None."""
    text = ASYMMETRIC_RE.sub("", strip_quoted(text))
    stack = []
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in PAIRS:
            if not stack or stack[-1] != PAIRS[ch]:
                return f"unbalanced '{ch}'"
            stack.pop()
    if stack:
        return f"unclosed '{stack[-1]}'"
    return None


def check_diagram(report, path, first_no, lines, mmdc):
    report.diagrams += 1
    body = meaningful_lines(first_no, lines)
    if not body:
        report.emit(path, first_no, "ERROR", "empty diagram")
        return
    type_no, type_line = body[0]
    m = re.match(r"[A-Za-z][\w-]*", type_line.strip())
    dtype = m.group(0) if m else ""
    if dtype not in KNOWN_TYPES:
        report.emit(path, type_no, "ERROR",
                    f"unknown diagram type '{dtype or type_line.strip()[:20]}'")
        return
    if dtype in ("flowchart", "graph"):
        rest = type_line.strip()[len(dtype):].split()
        if rest and rest[0] not in FLOW_DIRECTIONS and not rest[0].startswith("%%"):
            report.emit(path, type_no, "ERROR",
                        f"invalid direction '{rest[0]}' (use one of {', '.join(sorted(FLOW_DIRECTIONS))})")
    if len(body) == 1:
        report.emit(path, type_no, "ERROR", f"{dtype} diagram has no content after the type line")

    content = body[1:]
    if dtype not in FREE_TEXT_TYPES:
        for no, text in content:
            if text.replace("#quot;", "").count('"') % 2:
                report.emit(path, no, "ERROR", "unbalanced double quote")
    if dtype in LINE_BRACKET_TYPES:
        for no, text in content:
            problem = check_line_brackets(text)
            if problem:
                report.emit(path, no, "ERROR", f"{problem} in: {text.strip()[:60]}")
    if dtype in BLOCK_BRACE_TYPES:
        depth = 0
        for no, text in content:
            t = strip_quoted(text)
            if dtype == "erDiagram":
                t = ER_RELATION_RE.sub("", t)
            depth += t.count("{") - t.count("}")
            if depth < 0:
                report.emit(path, no, "ERROR", "unbalanced '}'")
                depth = 0
        if depth > 0:
            report.emit(path, type_no, "ERROR", f"{depth} unclosed '{{' block(s)")
    if dtype in ("flowchart", "graph"):
        check_flowchart_warnings(report, path, content)
    if mmdc:
        error = run_mmdc(mmdc, "\n".join(lines) + "\n")
        if error:
            report.emit(path, first_no, "ERROR", f"mmdc: {error}")


def check_flowchart_warnings(report, path, content):
    labels = {}
    for no, text in content:
        stripped = text.strip()
        if stripped.startswith(("subgraph", "click", "style", "classDef", "class ", "linkStyle")):
            continue
        for m in NODE_DEF_RE.finditer(text):
            node = m.group(1)
            label = (m.group(2) if m.group(2) is not None else m.group(3) or "").strip()
            if node in labels and labels[node][1] != label:
                report.emit(path, no, "WARNING",
                            f"node '{node}' redefined with a different label "
                            f"(first defined on line {labels[node][0]})")
            labels.setdefault(node, (no, label))
        unquoted = BR_TAG_RE.sub("", re.sub(r"\"[^\"]*\"", "", text))
        for lm in re.finditer(r"\[([^\]]*)\]|\(([^)]*)\)|\{([^}]*)\}", unquoted):
            inner = next(g for g in lm.groups() if g is not None)
            if "<" in inner or (">" in inner and not inner.lstrip().startswith(">")):
                report.emit(path, no, "WARNING",
                            "unescaped '<' or '>' in an unquoted label; quote the label or use #lt; / #gt;")
                break
        if stripped != "end" and BARE_END_RE.search(strip_quoted(text)):
            report.emit(path, no, "WARNING",
                        "'end' used as a node id or label breaks flowcharts; use 'End' or quote it")


def run_mmdc(mmdc, text):
    """Parse one diagram with mermaid-cli; return an error message or None."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "diagram.mmd")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            proc = subprocess.run([mmdc, "-i", src, "-o", os.path.join(tmp, "diagram.svg")],
                                  capture_output=True, text=True, timeout=MMDC_TIMEOUT)
        if proc.returncode != 0:
            lines = [ln for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip()]
            return lines[0].strip()[:200] if lines else f"exit code {proc.returncode}"
    except subprocess.TimeoutExpired:
        return f"timed out after {MMDC_TIMEOUT}s"
    except OSError as exc:
        return f"could not run mmdc: {exc}"
    return None


def check_file(report, path, mmdc):
    report.files += 1
    shown = path.replace(os.sep, "/")
    try:
        lines, bad = read_lines(path)
    except OSError as exc:
        report.emit(shown, 1, "ERROR", f"cannot read file: {exc}")
        return
    if bad:
        report.emit(shown, 1, "WARNING", "file is not valid UTF-8; decoded with replacement characters")
    blocks, unterminated = extract_blocks(lines, path.lower().endswith(".mmd"))
    for no in unterminated:
        report.emit(shown, no, "ERROR", "unterminated mermaid code fence")
    for first_no, block in blocks:
        check_diagram(report, shown, first_no, block, mmdc)


def iter_files(target):
    if os.path.isfile(target):
        yield target
        return
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.lower().endswith((".md", ".mmd")):
                yield os.path.join(dirpath, name)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Check Mermaid diagrams in .md (fenced blocks) and .mmd files.")
    p.add_argument("path", nargs="+", help="File or directory to scan (several allowed)")
    args = p.parse_args(argv)

    for target in args.path:
        if not os.path.exists(target):
            print(f"error: path does not exist: {target}", file=sys.stderr)
            return 2
    mmdc = shutil.which("mmdc")
    if not mmdc:
        print("INFO: mmdc not found, heuristic checks only")
    report = Report()
    for target in args.path:
        for path in iter_files(target):
            check_file(report, path, mmdc)
    print(f"Checked {report.files} file(s), {report.diagrams} diagram(s): "
          f"{report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
