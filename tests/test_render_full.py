import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "render_wireframe.py"
EXAMPLE = ROOT / "project-blueprint" / "assets" / "templates" / "wireframe-spec.example.json"
SVG_NS = "{http://www.w3.org/2000/svg}"

ALL_ELEMENTS = [
    {"type": "header", "text": "Header"},
    {"type": "text", "text": "Some body text that is long enough to wrap onto a second line here."},
    {"type": "image", "alt": "Cover photo", "caption": "A caption"},
    {"type": "input", "label": "Email", "placeholder": "you@mail.com"},
    {"type": "textarea", "label": "Notes", "placeholder": "Write..."},
    {"type": "select", "label": "Language", "options": ["English", "German"]},
    {"type": "checkbox", "label": "Remember me", "checked": True},
    {"type": "radio", "label": "Plan", "options": ["Free", "Pro"]},
    {"type": "radio", "label": "Single radio"},
    {"type": "toggle", "label": "Notifications", "on": True},
    {"type": "toggle", "label": "Dark mode"},
    {"type": "button", "text": "Save", "primary": True},
    {"type": "link", "text": "Help"},
    {"type": "list", "items": ["One", "Two", "Three"]},
    {"type": "card", "title": "Card", "text": "Card body text"},
    {"type": "table", "columns": ["Title", "Author"], "rows": [["Dune", "Herbert"]]},
    {"type": "tabs", "items": ["All", "Read"], "active": 1},
    {"type": "nav", "items": ["Home", "Books", "Me"]},
    {"type": "modal", "title": "Delete?", "text": "This cannot be undone.", "actions": ["Cancel", "Delete"]},
    {"type": "divider"},
    {"type": "spacer", "height": 10},
    {"type": "row", "children": [{"type": "button", "text": "A"}, {"type": "button", "text": "B"}]},
    {"type": "column", "children": [{"type": "text", "text": "c1"}, {"type": "text", "text": "c2"}]},
]


def run(spec_path, out, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(spec_path), "--out", str(out), *extra],
                          capture_output=True, text=True)


def write_spec(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def nested(depth):
    node = {"type": "button", "text": "leaf"}
    for i in range(depth):
        node = {"type": "row" if i % 2 else "column", "children": [node]}
    return node


def one_screen(elements, **extra):
    screen = {"id": "s", "name": "S", "elements": elements}
    screen.update(extra)
    return {"project": "P", "screens": [screen]}


@pytest.mark.parametrize("element", ALL_ELEMENTS, ids=lambda e: e["type"])
def test_every_element_type_renders(tmp_path, element):
    proc = run(write_spec(tmp_path, one_screen([element])), tmp_path / "out")
    assert proc.returncode == 0, proc.stderr
    raw = (tmp_path / "out" / "s.svg").read_text(encoding="utf-8")
    assert f"[{element['type']}]" not in raw
    ET.fromstring(raw)


def test_all_elements_together_and_deterministic(tmp_path):
    spec = write_spec(tmp_path, one_screen(ALL_ELEMENTS))
    assert run(spec, tmp_path / "a").returncode == 0
    assert run(spec, tmp_path / "b", "--html").returncode == 0
    assert (tmp_path / "a" / "s.svg").read_bytes() == (tmp_path / "b" / "s.svg").read_bytes()
    ET.fromstring((tmp_path / "a" / "s.svg").read_bytes())


def test_nested_row_column_three_levels_ok(tmp_path):
    proc = run(write_spec(tmp_path, one_screen([nested(3)])), tmp_path / "out")
    assert proc.returncode == 0, proc.stderr
    raw = (tmp_path / "out" / "s.svg").read_text(encoding="utf-8")
    assert ">leaf<" in raw


def test_nested_row_column_depth_four_fails(tmp_path):
    proc = run(write_spec(tmp_path, one_screen([nested(4)])), tmp_path / "out")
    assert proc.returncode != 0
    assert "screens[0].elements[0].children[0].children[0].children[0]" in proc.stderr
    assert "deeper than 3 levels" in proc.stderr


def test_row_children_are_side_by_side(tmp_path):
    spec = one_screen([{"type": "row", "children": [
        {"type": "button", "text": "A"}, {"type": "button", "text": "B"}]}])
    assert run(write_spec(tmp_path, spec), tmp_path / "out").returncode == 0
    root = ET.fromstring((tmp_path / "out" / "s.svg").read_bytes())
    rects = [r for r in root.iter(SVG_NS + "rect") if r.get("height") == "44"]
    assert len(rects) == 2 and rects[0].get("y") == rects[1].get("y")
    assert rects[0].get("x") != rects[1].get("x")


def test_bad_spacer_and_active_rejected(tmp_path):
    spec = one_screen([{"type": "spacer", "height": 0}, {"type": "tabs", "items": ["a"], "active": -1}])
    proc = run(write_spec(tmp_path, spec), tmp_path / "out")
    assert proc.returncode != 0
    assert "screens[0].elements[0].height" in proc.stderr
    assert "screens[0].elements[1].active" in proc.stderr


def test_screen_flow_written_with_edges(tmp_path):
    assert run(EXAMPLE, tmp_path / "out").returncode == 0
    md = (tmp_path / "out" / "screen-flow.md").read_text(encoding="utf-8")
    assert "flowchart" in md and "```mermaid" in md
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for s in spec["screens"]:
        assert f'{s["id"]}["{s["name"]}"]' in md
        for link in s["navigates_to"]:
            assert f'{s["id"]} -->|"{link["element"]}"| {link["screen"]}' in md


def test_screen_flow_escapes_and_sanitizes(tmp_path):
    spec = {"project": "P", "screens": [
        {"id": "start", "name": 'Say "hi" <b>', "elements": [{"type": "button", "text": "Go"}],
         "navigates_to": [{"element": 'A "x" #1', "screen": "end"}]},
        {"id": "end", "name": "End", "elements": []},
        {"id": "start--error", "name": "Err", "elements": []},
    ]}
    proc = run(write_spec(tmp_path, spec), tmp_path / "out")
    assert proc.returncode == 0, proc.stderr
    md = (tmp_path / "out" / "screen-flow.md").read_text(encoding="utf-8")
    assert "end_screen" in md and 'start__error["Err"]' in md
    assert "#quot;" in md and "#lt;b#gt;" in md and "#35;1" in md


def test_unreachable_screen_warns_on_stderr(tmp_path):
    spec = {"project": "P", "screens": [
        {"id": "home", "name": "Home", "elements": [], "navigates_to": [{"element": "x", "screen": "a"}]},
        {"id": "a", "name": "A", "elements": []},
        {"id": "orphan", "name": "Orphan", "elements": []},
    ]}
    proc = run(write_spec(tmp_path, spec), tmp_path / "out")
    assert proc.returncode == 0
    assert "screen 'orphan' has no incoming navigation" in proc.stderr
    assert "screen 'home'" not in proc.stderr and "screen 'a'" not in proc.stderr


def test_example_has_no_reachability_warnings(tmp_path):
    proc = run(EXAMPLE, tmp_path / "out")
    assert proc.returncode == 0 and "warning" not in proc.stderr


def test_html_gallery(tmp_path):
    assert run(EXAMPLE, tmp_path / "out", "--html").returncode == 0
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "prefers-color-scheme: dark" in html
    for name in ("Login", "Dashboard", "Settings"):
        assert f"<h2>{name}</h2>" in html
    assert "Shown to unauthenticated users" in html
    assert html.count("<svg") == 6  # light + dark variant of each screen
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html
    assert "<link " not in html and "<script" not in html


def test_html_not_written_without_flag(tmp_path):
    assert run(EXAMPLE, tmp_path / "out").returncode == 0
    assert not (tmp_path / "out" / "index.html").exists()


def test_html_is_deterministic_and_escaped(tmp_path):
    spec = one_screen([{"type": "text", "text": "x"}], name="A & <B>", notes="n < m")
    spec["project"] = "Proj & Co"
    path = write_spec(tmp_path, spec)
    assert run(path, tmp_path / "a", "--html").returncode == 0
    assert run(path, tmp_path / "b", "--html").returncode == 0
    a = (tmp_path / "a" / "index.html").read_bytes()
    assert a == (tmp_path / "b" / "index.html").read_bytes()
    text = a.decode("utf-8")
    assert "Proj &amp; Co" in text and "A &amp; &lt;B&gt;" in text and "n &lt; m" in text
