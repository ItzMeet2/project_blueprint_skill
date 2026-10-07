#!/usr/bin/env python3
"""Export the story tables of a sprint-plan markdown file to CSV and JSON.

Usage: export_sprint.py <sprint-plan.md> [--csv out.csv] [--json out.json]

Every markdown table whose header is exactly
  | ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |
is parsed (other tables and tables inside code fences are ignored) and validated:
  - IDs are unique; Points is one of 1, 2, 3, 5, 8; Priority is Must, Should, Could or Won't
  - Sprint is a whole number >= 1
  - Depends On lists existing story IDs (separated by comma, semicolon or space);
    "—" (also "-", "–", "none" or an empty cell) means no dependency
  - dependencies contain no cycles
Warnings (exit code stays 0): a sprint plans more than 10% over its stated
"Capacity: N" line, or a story depends on a story scheduled in a later sprint.

Problems print as `path:line: ERROR message` on stderr and nothing is written.
Exit code: 0 success, 1 invalid input, 2 unreadable file. Standard library only.
"""

import argparse
import csv
import json
import os
import re
import sys

COLUMNS = ["ID", "Epic", "Story", "Points", "Priority", "Depends On", "Sprint",
           "Acceptance Criteria"]
VALID_POINTS = (1, 2, 3, 5, 8)
PRIORITIES = ("Must", "Should", "Could", "Won't")
NO_DEPENDENCY = {"", "—", "–", "-", "none", "n/a"}
CAPACITY_TOLERANCE = 1.10

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
SPRINT_HEADING_RE = re.compile(r"^\s*#{1,6}\s*Sprint\s+(\d+)\b", re.IGNORECASE)
CAPACITY_RE = re.compile(r"^\s*[-*]?\s*\**\s*Capacity\s*:?\s*\**\s*(\d+)\b", re.IGNORECASE)
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


def split_row(line):
    """Split a markdown table row into stripped cells, honoring \\| escapes."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells, current, i = [], [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if text[i] == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(text[i])
        i += 1
    cells.append("".join(current).strip())
    return cells


def is_separator(line):
    cells = split_row(line)
    return bool(cells) and all(SEPARATOR_CELL_RE.match(c) for c in cells)


def parse_plan(text):
    """Return (rows, capacities, global_capacity, errors).

    rows: list of dicts with 'line' and the table columns. capacities maps
    sprint number -> capacity from a 'Capacity: N' line under that sprint heading.
    """
    lines = text.splitlines()
    rows, errors = [], []
    capacities, global_capacity = {}, None
    current_sprint = None
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        fm = FENCE_RE.match(line)
        if fence:
            if fm and fm.group(1)[0] == fence[0] and len(fm.group(1)) >= len(fence):
                fence = None
            i += 1
            continue
        if fm:
            fence = fm.group(1)
            i += 1
            continue
        hm = SPRINT_HEADING_RE.match(line)
        if hm:
            current_sprint = int(hm.group(1))
        cm = CAPACITY_RE.match(line)
        if cm:
            if current_sprint is None:
                global_capacity = int(cm.group(1))
            else:
                capacities[current_sprint] = int(cm.group(1))
        if line.strip().startswith("|") and split_row(line) == COLUMNS:
            if i + 1 >= len(lines) or not is_separator(lines[i + 1]):
                errors.append((i + 1, "story table header found but the separator row "
                                      "(|----|----|...) is missing"))
                i += 1
                continue
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = split_row(lines[j])
                if len(cells) != len(COLUMNS):
                    errors.append((j + 1, f"expected {len(COLUMNS)} columns, got {len(cells)}"))
                else:
                    row = dict(zip(COLUMNS, cells))
                    row["line"] = j + 1
                    rows.append(row)
                j += 1
            i = j
            continue
        i += 1
    return rows, capacities, global_capacity, errors


def parse_dependencies(value):
    if value.strip().lower() in NO_DEPENDENCY:
        return []
    return [d for d in re.split(r"[,;\s]+", value.strip()) if d]


def find_cycle(graph):
    """Return one dependency cycle as a list of ids (first == last), or None."""
    state = {}  # id -> 1 visiting, 2 done

    def visit(node, stack):
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if state.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if dep not in state:
                found = visit(dep, stack)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if node not in state:
            found = visit(node, [])
            if found:
                return found
    return None


def validate(rows):
    """Return (stories, errors) where stories have typed fields."""
    errors, stories, seen = [], [], {}
    for row in rows:
        ln = row["line"]
        sid = row["ID"]
        if not sid:
            errors.append((ln, "ID must not be empty"))
            continue
        if sid in seen:
            errors.append((ln, f"duplicate ID '{sid}' (first used on line {seen[sid]})"))
            continue
        seen[sid] = ln
        points = None
        try:
            points = int(row["Points"])
        except ValueError:
            pass
        if points not in VALID_POINTS:
            hint = "; split stories larger than 8 points" if (points or 0) > 8 else ""
            errors.append((ln, f"{sid}: Points must be one of "
                               f"{', '.join(map(str, VALID_POINTS))} (got '{row['Points']}'){hint}"))
        priority = row["Priority"].replace("’", "'")
        if priority not in PRIORITIES:
            errors.append((ln, f"{sid}: Priority must be one of {', '.join(PRIORITIES)} "
                               f"(got '{row['Priority']}')"))
        sprint = None
        if re.fullmatch(r"\d+", row["Sprint"]) and int(row["Sprint"]) >= 1:
            sprint = int(row["Sprint"])
        else:
            errors.append((ln, f"{sid}: Sprint must be a whole number >= 1 (got '{row['Sprint']}')"))
        stories.append({
            "id": sid, "epic": row["Epic"], "story": row["Story"], "points": points,
            "priority": priority, "depends_on": parse_dependencies(row["Depends On"]),
            "sprint": sprint, "acceptance_criteria": row["Acceptance Criteria"],
            "_line": ln, "_depends_raw": row["Depends On"],
        })
    ids = {s["id"] for s in stories}
    graph = {}
    for s in stories:
        for dep in s["depends_on"]:
            if dep not in ids:
                errors.append((s["_line"], f"{s['id']}: Depends On references unknown ID '{dep}'"))
        graph[s["id"]] = [d for d in s["depends_on"] if d in ids]
    cycle = find_cycle(graph)
    if cycle:
        line = next(s["_line"] for s in stories if s["id"] == cycle[0])
        errors.append((line, "dependency cycle: " + " -> ".join(cycle)))
    return stories, errors


def build_warnings(stories, capacities, global_capacity):
    warnings = []
    by_id = {s["id"]: s for s in stories}
    for s in stories:
        for dep in s["depends_on"]:
            d = by_id.get(dep)
            if d and s["sprint"] and d["sprint"] and d["sprint"] > s["sprint"]:
                warnings.append((s["_line"], f"{s['id']} (sprint {s['sprint']}) depends on {dep}, "
                                             f"which is scheduled later (sprint {d['sprint']})"))
    for n, planned in sorted(planned_points(stories).items()):
        cap = capacities.get(n, global_capacity)
        if cap is not None and planned > cap * CAPACITY_TOLERANCE:
            warnings.append((0, f"sprint {n} plans {planned} points but its capacity is {cap} "
                                f"(more than 10% over)"))
    return warnings


def planned_points(stories):
    totals = {}
    for s in stories:
        if s["sprint"] and s["points"]:
            totals[s["sprint"]] = totals.get(s["sprint"], 0) + s["points"]
    return totals


def build_json(stories, capacities, global_capacity, source):
    totals = planned_points(stories)
    sprints = []
    for n in sorted({s["sprint"] for s in stories}):
        group = [s for s in stories if s["sprint"] == n]
        cap = capacities.get(n, global_capacity)
        sprints.append({
            "sprint": n,
            "capacity": cap,
            "planned_points": totals.get(n, 0),
            "over_capacity": cap is not None and totals.get(n, 0) > cap * CAPACITY_TOLERANCE,
            "story_count": len(group),
            "stories": [{k: v for k, v in s.items() if not k.startswith("_")} for s in group],
        })
    return {
        "source": os.path.basename(source),
        "sprints": sprints,
        "totals": {"stories": len(stories), "points": sum(totals.values())},
    }


def write_csv(path, stories, rows_by_id):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for s in stories:
            row = rows_by_id[s["id"]]
            writer.writerow([row[c] for c in COLUMNS])


def write_json(path, data):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def ensure_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Parse the story tables of a sprint-plan.md and export CSV / JSON.")
    p.add_argument("plan", help="Path to sprint-plan.md")
    p.add_argument("--csv", metavar="FILE", help="Write the stories as CSV")
    p.add_argument("--json", metavar="FILE", help="Write the stories grouped by sprint as JSON")
    args = p.parse_args(argv)

    try:
        with open(args.plan, "rb") as fh:
            text = fh.read().decode("utf-8-sig")
    except OSError as exc:
        print(f"error: cannot read {args.plan}: {exc}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print(f"error: {args.plan} is not valid UTF-8", file=sys.stderr)
        return 1

    shown = args.plan.replace(os.sep, "/")
    rows, capacities, global_capacity, errors = parse_plan(text)
    if not rows and not errors:
        errors.append((1, "no story table found; expected a table with the header "
                          "| " + " | ".join(COLUMNS) + " |"))
    stories, problems = validate(rows)
    errors.extend(problems)
    if errors:
        for line, message in sorted(errors):
            print(f"{shown}:{line}: ERROR {message}", file=sys.stderr)
        print(f"{len(errors)} error(s); nothing written", file=sys.stderr)
        return 1

    for line, message in build_warnings(stories, capacities, global_capacity):
        where = f"{shown}:{line}:" if line else f"{shown}:"
        print(f"{where} WARNING {message}", file=sys.stderr)

    rows_by_id = {r["ID"]: r for r in rows}
    try:
        if args.csv:
            write_csv(args.csv, stories, rows_by_id)
        if args.json:
            write_json(args.json, build_json(stories, capacities, global_capacity, args.plan))
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1
    points = sum(planned_points(stories).values())
    sprint_count = len({s["sprint"] for s in stories})
    print(f"Parsed {len(stories)} stories ({points} points) in {sprint_count} sprint(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
