import copy
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "render_wireframe.py"
EXAMPLE = ROOT / "project-blueprint" / "assets" / "templates" / "wireframe-spec.example.json"
SVG_NS = "{http://www.w3.org/2000/svg}"


def load_example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def render(spec_path, out, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(spec_path), "--out", str(out), *extra],
                          capture_output=True, text=True)


def write_spec(tmp_path, spec, name="spec.json"):
    path = tmp_path / name
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_example_renders_one_svg_per_screen(tmp_path):
    proc = render(EXAMPLE, tmp_path / "out")
    assert proc.returncode == 0, proc.stderr
    names = sorted(p.name for p in (tmp_path / "out").glob("*.svg"))
    assert names == ["dashboard.svg", "login.svg", "settings.svg"]


def test_output_is_valid_xml(tmp_path):
    assert render(EXAMPLE, tmp_path / "out").returncode == 0
    for svg in (tmp_path / "out").glob("*.svg"):
        root = ET.fromstring(svg.read_bytes())
        assert root.tag == SVG_NS + "svg"
        assert root.get("width") == "390"


def test_output_is_deterministic(tmp_path):
    assert render(EXAMPLE, tmp_path / "a").returncode == 0
    assert render(EXAMPLE, tmp_path / "b").returncode == 0
    for svg in (tmp_path / "a").glob("*.svg"):
        assert svg.read_bytes() == (tmp_path / "b" / svg.name).read_bytes()


def test_dark_theme_differs_from_light(tmp_path):
    assert render(EXAMPLE, tmp_path / "l").returncode == 0
    assert render(EXAMPLE, tmp_path / "d", "--theme", "dark").returncode == 0
    assert (tmp_path / "l" / "login.svg").read_bytes() != (tmp_path / "d" / "login.svg").read_bytes()


def test_invalid_spec_names_json_path(tmp_path):
    spec = load_example()
    spec["screens"][1]["elements"] = [
        {"type": "header", "text": "H"},
        {"type": "text", "text": "T"},
        {"type": "input", "placeholder": "x"},
    ]
    proc = render(write_spec(tmp_path, spec), tmp_path / "out")
    assert proc.returncode != 0
    assert "screens[1].elements[2]: input requires 'label'" in proc.stderr
    assert not (tmp_path / "out").exists()


def test_unknown_type_and_bad_navigation_reported(tmp_path):
    spec = load_example()
    spec["screens"][0]["elements"].append({"type": "hologram"})
    spec["screens"][0]["navigates_to"].append({"element": "Go", "screen": "nowhere"})
    proc = render(write_spec(tmp_path, spec), tmp_path / "out")
    assert proc.returncode != 0
    assert "screens[0].elements[5]: unknown element type 'hologram'" in proc.stderr
    assert "screens[0].navigates_to[1]: unknown screen 'nowhere'" in proc.stderr


def test_invalid_json_and_missing_file_fail(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert render(bad, tmp_path / "o").returncode != 0
    assert render(tmp_path / "missing.json", tmp_path / "o").returncode != 0


def test_text_is_xml_escaped(tmp_path):
    tricky = "A & B <x> \"q\" 'a'"
    spec = {"project": "P", "screens": [{
        "id": "s", "name": "S & <T>", "elements": [
            {"type": "text", "text": tricky},
            {"type": "button", "text": tricky},
            {"type": "input", "label": tricky, "placeholder": tricky},
        ]}]}
    assert render(write_spec(tmp_path, spec), tmp_path / "out").returncode == 0
    raw = (tmp_path / "out" / "s.svg").read_text(encoding="utf-8")
    assert "A &amp; B &lt;x&gt;" in raw
    assert "<x>" not in raw
    root = ET.fromstring(raw)
    texts = [t.text for t in root.iter(SVG_NS + "text")]
    assert tricky in texts
    assert root.find(SVG_NS + "title").text == "S & <T>"


def test_core_elements_render_without_placeholders(tmp_path):
    spec = {"project": "P", "screens": [{
        "id": "all", "name": "All", "elements": [
            {"type": "header", "text": "H"}, {"type": "text", "text": "T"},
            {"type": "input", "label": "L", "secret": True},
            {"type": "button", "text": "B", "primary": True},
            {"type": "link", "text": "Lk"}, {"type": "divider"}, {"type": "spacer", "height": 8},
            {"type": "table", "columns": ["a"]},
            {"type": "row", "children": [{"type": "button", "text": "x"}]},
        ]}]}
    assert render(write_spec(tmp_path, spec), tmp_path / "out").returncode == 0
    raw = (tmp_path / "out" / "all.svg").read_text(encoding="utf-8")
    assert "[table]" not in raw and "[row]" not in raw
    ET.fromstring(raw)


def test_desktop_viewport_and_tall_content(tmp_path):
    spec = copy.deepcopy(load_example())
    spec["screens"][0]["viewport"] = "desktop"
    spec["screens"][1]["elements"] = [{"type": "spacer", "height": 2000}]
    assert render(write_spec(tmp_path, spec), tmp_path / "out").returncode == 0
    login = ET.fromstring((tmp_path / "out" / "login.svg").read_bytes())
    assert (login.get("width"), login.get("height")) == ("1280", "800")
    dash = ET.fromstring((tmp_path / "out" / "dashboard.svg").read_bytes())
    assert int(dash.get("height")) > 2000


def test_help_works():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0 and "--theme" in proc.stdout
