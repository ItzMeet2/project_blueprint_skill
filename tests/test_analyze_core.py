import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "analyze_project.py"
SAMPLE = ROOT / "examples" / "sample-dotnet-mvc"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


@pytest.fixture(scope="module")
def sample_result(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    proc = run(SAMPLE, "--out", out)
    assert proc.returncode == 0, proc.stderr
    raw = (out / "analysis.raw.json").read_text(encoding="utf-8")
    return raw, json.loads(raw), proc.stdout


def test_csharp_detected(sample_result):
    _, data, _ = sample_result
    assert "C#" in data["languages"]


def test_csproj_found(sample_result):
    _, data, _ = sample_result
    assert any(s["marker"].endswith(".csproj") for s in data["stack"])


def test_program_cs_entry_point(sample_result):
    _, data, _ = sample_result
    assert "Program.cs" in data["entry_points"]


def test_env_listed_but_content_never_leaks(sample_result):
    raw, data, stdout = sample_result
    assert ".env" in data["sensitive_files_present"]
    assert "do-not-read-me" not in raw
    assert "do-not-read-me" not in stdout


def test_key_dirs_have_roles(sample_result):
    _, data, _ = sample_result
    paths = {d["path"] for d in data["key_dirs"]}
    assert {"Controllers/", "Models/", "Views/", "Data/"} <= paths


def test_required_keys_present(sample_result):
    _, data, _ = sample_result
    for key in ("scanned_root", "file_stats", "languages", "stack", "key_dirs",
                "entry_points", "sensitive_files_present", "truncated"):
        assert key in data
    assert data["truncated"] is False


def test_nonexistent_path_fails(tmp_path):
    proc = run(tmp_path / "nope", "--out", tmp_path / "out")
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_max_files_truncates(tmp_path):
    out = tmp_path / "out"
    assert run(SAMPLE, "--out", out, "--max-files", "3").returncode == 0
    data = json.loads((out / "analysis.raw.json").read_text(encoding="utf-8"))
    assert data["truncated"] is True
    assert data["file_stats"]["files_scanned"] == 3


def test_skips_ignored_dirs_and_gitignore(tmp_path):
    proj = tmp_path / "proj"
    (proj / "node_modules").mkdir(parents=True)
    (proj / "node_modules" / "x.js").write_text("1")
    (proj / "logs").mkdir()
    (proj / "logs" / "a.py").write_text("1")
    (proj / "keep.py").write_text("1")
    (proj / "debug.log").write_text("1")
    (proj / ".gitignore").write_text("logs/\n*.log\n")
    out = tmp_path / "out"
    assert run(proj, "--out", out).returncode == 0
    data = json.loads((out / "analysis.raw.json").read_text(encoding="utf-8"))
    assert data["languages"] == {"Python": 1}
    assert ".log" not in data["file_stats"]["by_extension"]


def test_secret_files_not_read(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "server.pem").write_text("SECRET-PEM")
    (proj / "secrets.json").write_text("SECRET-JSON")
    (proj / "id.key").write_text("SECRET-KEY")
    out = tmp_path / "out"
    assert run(proj, "--out", out).returncode == 0
    raw = (out / "analysis.raw.json").read_text(encoding="utf-8")
    assert "SECRET" not in raw
    data = json.loads(raw)
    assert sorted(data["sensitive_files_present"]) == ["id.key", "secrets.json", "server.pem"]


def test_help_works():
    proc = run("--help")
    assert proc.returncode == 0
    assert "--max-files" in proc.stdout
