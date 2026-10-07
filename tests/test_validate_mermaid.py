import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "validate_mermaid.py"
FIXTURES = ROOT / "tests" / "fixtures"

spec = importlib.util.spec_from_file_location("validate_mermaid", SCRIPT)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


def run(*paths):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, paths)],
                          capture_output=True, text=True)


def test_valid_file_passes_with_three_diagram_types():
    proc = run(FIXTURES / "mermaid-valid.md")
    assert proc.returncode == 0, proc.stdout
    assert "4 diagram(s): 0 error(s), 0 warning(s)" in proc.stdout


def test_unknown_diagram_type_is_error_with_line():
    proc = run(FIXTURES / "mermaid-unknown-type.md")
    assert proc.returncode == 1
    assert "mermaid-unknown-type.md:2: ERROR unknown diagram type 'flowchrt'" in proc.stdout


def test_unbalanced_brackets_and_quotes_are_errors():
    proc = run(FIXTURES / "mermaid-unbalanced.md")
    assert proc.returncode == 1
    out = proc.stdout
    assert "mermaid-unbalanced.md:5: ERROR unclosed '['" in out
    assert "mermaid-unbalanced.md:6: ERROR unclosed '('" in out
    assert "mermaid-unbalanced.md:13: ERROR unbalanced double quote" in out


def test_empty_mmd_is_error_and_empty_md_is_fine():
    proc = run(FIXTURES / "mermaid-empty.mmd")
    assert proc.returncode == 1 and "ERROR empty diagram" in proc.stdout
    proc = run(FIXTURES / "mermaid-empty.md")
    assert proc.returncode == 0 and "0 diagram(s)" in proc.stdout


def test_warnings_do_not_fail():
    proc = run(FIXTURES / "mermaid-warnings.md")
    assert proc.returncode == 0, proc.stdout
    out = proc.stdout
    assert "WARNING node 'A' redefined with a different label (first defined on line 3)" in out
    assert "WARNING 'end' used as a node id" in out
    assert "WARNING unescaped '<' or '>'" in out
    assert "0 error(s), 3 warning(s)" in out


def test_spec_md_has_no_errors():
    proc = run(ROOT / "docs" / "SPEC.md")
    assert proc.returncode == 0, proc.stdout
    assert "ERROR" not in proc.stdout


def test_directory_scan_finds_md_and_mmd():
    proc = run(FIXTURES)
    assert proc.returncode == 1
    assert "mermaid-empty.mmd:1: ERROR" in proc.stdout
    assert "mermaid-unknown-type.md:2: ERROR" in proc.stdout
    assert "mermaid-valid.md" not in proc.stdout


def test_missing_path_exits_2(tmp_path):
    proc = run(tmp_path / "nope")
    assert proc.returncode == 2 and "does not exist" in proc.stderr


def test_mmdc_missing_prints_info(monkeypatch):
    proc = run(FIXTURES / "mermaid-valid.md")
    if vm.shutil.which("mmdc") is None:
        assert "INFO: mmdc not found, heuristic checks only" in proc.stdout


def test_non_utf8_and_unterminated_fence_do_not_crash(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"```mermaid\nflowchart TD\n  A[caf\xe9] --> B\n```\n")
    proc = run(bad)
    assert proc.returncode == 0, proc.stdout
    assert "WARNING file is not valid UTF-8" in proc.stdout
    open_fence = tmp_path / "open.md"
    open_fence.write_text("```mermaid\nflowchart TD\n  A --> B\n", encoding="utf-8")
    proc = run(open_fence)
    assert proc.returncode == 1 and "unterminated mermaid code fence" in proc.stdout


def test_invalid_flowchart_direction(tmp_path):
    f = tmp_path / "d.mmd"
    f.write_text("flowchart XY\n  A --> B\n", encoding="utf-8")
    proc = run(f)
    assert proc.returncode == 1 and "invalid direction 'XY'" in proc.stdout


def test_type_line_only_is_error(tmp_path):
    f = tmp_path / "t.mmd"
    f.write_text("flowchart TD\n", encoding="utf-8")
    proc = run(f)
    assert proc.returncode == 1 and "no content" in proc.stdout


def test_frontmatter_and_comments_are_skipped(tmp_path):
    f = tmp_path / "f.mmd"
    f.write_text("---\ntitle: Demo\n---\n%% a comment (\nflowchart LR\n  A --> B\n", encoding="utf-8")
    proc = run(f)
    assert proc.returncode == 0, proc.stdout


def test_mmdc_errors_are_reported(tmp_path, monkeypatch, capsys):
    f = tmp_path / "m.mmd"
    f.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    monkeypatch.setattr(vm.shutil, "which", lambda name: "/fake/mmdc")
    monkeypatch.setattr(vm, "run_mmdc", lambda mmdc, text: "Parse error on line 2")
    assert vm.main([str(f)]) == 1
    assert "ERROR mmdc: Parse error on line 2" in capsys.readouterr().out
    monkeypatch.setattr(vm, "run_mmdc", lambda mmdc, text: None)
    assert vm.main([str(f)]) == 0
