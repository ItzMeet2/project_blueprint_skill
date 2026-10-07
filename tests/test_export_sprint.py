import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "export_sprint.py"
FIXTURES = ROOT / "tests" / "fixtures"
TEMPLATE = ROOT / "project-blueprint" / "assets" / "templates" / "sprint-plan.md"
HEADER = ("| ID | Epic | Story | Points | Priority | Depends On | Sprint | Acceptance Criteria |\n"
          "|----|------|-------|--------|----------|------------|--------|---------------------|\n")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def plan(tmp_path, *rows, extra=""):
    path = tmp_path / "plan.md"
    path.write_text(extra + HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def row(sid="US-001", points="3", priority="Must", deps="—", sprint="1"):
    return f"| {sid} | Epic | As a user, I can x | {points} | {priority} | {deps} | {sprint} | Given a, then b |"


def test_valid_plan_exports_csv_and_json(tmp_path):
    csv_path, json_path = tmp_path / "out" / "plan.csv", tmp_path / "out" / "plan.json"
    proc = run(FIXTURES / "sprint-valid.md", "--csv", csv_path, "--json", json_path)
    assert proc.returncode == 0, proc.stderr
    assert "Parsed 5 stories (24 points) in 2 sprint(s)" in proc.stdout

    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["ID", "Epic", "Story", "Points", "Priority", "Depends On", "Sprint",
                       "Acceptance Criteria"]
    assert len(rows) == 6  # header + 5 stories; the code-fenced duplicate is ignored
    assert rows[3][2] == "As a reader, I can add a book | with an ISBN"
    assert rows[5][5] == "US-002, US-003"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["source"] == "sprint-valid.md"
    assert data["totals"] == {"stories": 5, "points": 24}
    s1, s2 = data["sprints"]
    assert (s1["sprint"], s1["capacity"], s1["planned_points"], s1["story_count"]) == (1, 20, 16, 3)
    assert (s2["sprint"], s2["capacity"], s2["planned_points"]) == (2, 10, 8)
    assert s1["over_capacity"] is False
    story = s2["stories"][1]
    assert story["id"] == "US-005" and story["depends_on"] == ["US-002", "US-003"]
    assert story["points"] == 3 and story["priority"] == "Won't"


def test_no_warnings_for_valid_plan():
    proc = run(FIXTURES / "sprint-valid.md")
    assert proc.returncode == 0 and proc.stderr == ""


def test_bad_points_rejected_with_split_hint(tmp_path):
    out = tmp_path / "o.json"
    proc = run(FIXTURES / "sprint-bad-points.md", "--json", out)
    assert proc.returncode == 1
    assert "sprint-bad-points.md:7: ERROR US-001: Points must be one of 1, 2, 3, 5, 8 (got '13')" in proc.stderr
    assert "split stories larger than 8 points" in proc.stderr
    assert "US-002: Points must be one of" in proc.stderr
    assert not out.exists()


def test_cycle_detected():
    proc = run(FIXTURES / "sprint-cycle.md")
    assert proc.returncode == 1
    assert "dependency cycle: US-001 -> US-003 -> US-002 -> US-001" in proc.stderr


def test_self_dependency_is_a_cycle(tmp_path):
    proc = run(plan(tmp_path, row("US-001", deps="US-001")))
    assert proc.returncode == 1 and "dependency cycle: US-001 -> US-001" in proc.stderr


def test_over_capacity_warns_but_succeeds():
    proc = run(FIXTURES / "sprint-over-capacity.md")
    assert proc.returncode == 0
    assert "WARNING sprint 1 plans 13 points but its capacity is 10" in proc.stderr
    assert "sprint 2" not in proc.stderr  # 11 of 10 is within the 10% tolerance


def test_dependency_in_later_sprint_warns(tmp_path):
    proc = run(plan(tmp_path, row("US-001", sprint="2"), row("US-002", deps="US-001", sprint="1")))
    assert proc.returncode == 0
    assert "US-002 (sprint 1) depends on US-001, which is scheduled later (sprint 2)" in proc.stderr


def test_unknown_dependency_duplicate_id_priority_sprint(tmp_path):
    proc = run(plan(tmp_path,
                    row("US-001", deps="US-404"),
                    row("US-001"),
                    row("US-002", priority="Maybe"),
                    row("US-003", sprint="soon")))
    assert proc.returncode == 1
    err = proc.stderr
    assert "unknown ID 'US-404'" in err
    assert "duplicate ID 'US-001'" in err
    assert "Priority must be one of Must, Should, Could, Won't (got 'Maybe')" in err
    assert "Sprint must be a whole number >= 1 (got 'soon')" in err


def test_wrong_column_count_and_missing_separator(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(HEADER + "| US-001 | Epic | too short |\n", encoding="utf-8")
    proc = run(path)
    assert proc.returncode == 1 and "expected 8 columns, got 3" in proc.stderr
    path.write_text(HEADER.splitlines()[0] + "\n| US-001 |\n", encoding="utf-8")
    proc = run(path)
    assert proc.returncode == 1 and "separator row" in proc.stderr


def test_no_matching_table_is_an_error(tmp_path):
    path = tmp_path / "p.md"
    path.write_text("| Name | Points |\n|---|---|\n| a | 3 |\n", encoding="utf-8")
    proc = run(path)
    assert proc.returncode == 1 and "no story table found" in proc.stderr


def test_template_placeholders_are_rejected():
    proc = run(TEMPLATE)
    assert proc.returncode == 1 and "Points must be one of" in proc.stderr


def test_missing_file_and_non_utf8(tmp_path):
    proc = run(tmp_path / "nope.md")
    assert proc.returncode == 2 and "cannot read" in proc.stderr
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\x00 not utf8 \x80")
    proc = run(bad)
    assert proc.returncode == 1 and "not valid UTF-8" in proc.stderr


def test_alternative_no_dependency_markers_and_multiple_tables(tmp_path):
    path = tmp_path / "p.md"
    path.write_text(
        "## Sprint 1\n" + HEADER + row("US-001", deps="-") + "\n" + row("US-002", deps="") + "\n\n"
        "## Sprint 2\n" + HEADER + row("US-003", deps="US-001; US-002", sprint="2") + "\n",
        encoding="utf-8")
    out = tmp_path / "o.json"
    proc = run(path, "--json", out)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [s["story_count"] for s in data["sprints"]] == [2, 1]
    assert data["sprints"][1]["stories"][0]["depends_on"] == ["US-001", "US-002"]


def test_help_works():
    proc = run("--help")
    assert proc.returncode == 0 and "--csv" in proc.stdout and "--json" in proc.stdout
