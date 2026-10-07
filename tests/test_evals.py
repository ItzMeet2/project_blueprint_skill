import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals" / "evals.json"


def load():
    return json.loads(EVALS.read_text(encoding="utf-8"))


def test_json_parses_with_skill_name():
    data = load()
    assert data["skill_name"] == "project-blueprint"
    assert isinstance(data["evals"], list)


def test_eight_evals_with_unique_ids():
    evals = load()["evals"]
    assert len(evals) == 8
    ids = [e["id"] for e in evals]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_required_fields_and_types():
    for e in load()["evals"]:
        assert isinstance(e["id"], int)
        assert isinstance(e["prompt"], str) and len(e["prompt"].strip()) > 10
        assert isinstance(e["files"], list) and all(isinstance(f, str) for f in e["files"])
        assert isinstance(e["should_trigger"], bool)
        assert isinstance(e["expectations"], list)
        assert 3 <= len(e["expectations"]) <= 5, f"eval {e['id']} needs 3 to 5 expectations"
        assert all(isinstance(x, str) and len(x.strip()) > 10 for x in e["expectations"])


def test_has_negative_and_positive_cases():
    triggers = [e["should_trigger"] for e in load()["evals"]]
    assert False in triggers
    assert triggers.count(True) >= 7


def test_referenced_files_exist():
    for e in load()["evals"]:
        for f in e["files"]:
            assert (ROOT / f).exists(), f"eval {e['id']} references missing file {f}"


def test_covers_the_required_scenarios():
    by_id = {e["id"]: e for e in load()["evals"]}
    assert "examples/sample-dotnet-mvc" in by_id[1]["files"]
    assert by_id[2]["files"] == [] and "idea" in by_id[2]["expectations"][2]
    assert "mobile" in by_id[3]["prompt"].lower()
    assert "flowchart" in by_id[4]["prompt"].lower()
    assert "3-sprint" in by_id[5]["prompt"]
    assert any(f.endswith("README.md") for f in by_id[6]["files"])
    assert "figure out what to build first" in by_id[7]["prompt"]
    assert by_id[8]["should_trigger"] is False and "null reference" in by_id[8]["prompt"].lower()


def test_evals_readme_exists_and_lists_every_eval():
    text = (ROOT / "evals" / "README.md").read_text(encoding="utf-8")
    for n in range(1, 9):
        assert f"| {n} |" in text
