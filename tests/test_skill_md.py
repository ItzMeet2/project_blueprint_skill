import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent / "project-blueprint"
SKILL_MD = SKILL_DIR / "SKILL.md"


def split_frontmatter(text):
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "SKILL.md must start with '---'"
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return lines[1:end], "\n".join(lines[end + 1:])


def parse_frontmatter(lines):
    """Tiny YAML subset: 'key: value' and 'key: >' with indented continuation lines."""
    data, key = {}, None
    for line in lines:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, value = m.group(1), m.group(2)
            data[key] = "" if value in (">", "|", ">-", "|-") else value
        elif key and line.startswith(" "):
            data[key] = (data[key] + " " + line.strip()).strip()
        elif line.strip():
            raise AssertionError(f"unparseable frontmatter line: {line!r}")
    return data


@pytest.fixture(scope="module")
def parts():
    text = SKILL_MD.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    return parse_frontmatter(front), body, text


def test_frontmatter_has_only_name_and_description(parts):
    front, _, _ = parts
    assert set(front) == {"name", "description"}


def test_name_matches_folder(parts):
    front, _, _ = parts
    assert front["name"] == SKILL_DIR.name == "project-blueprint"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", front["name"])


def test_description_length_and_triggers(parts):
    front, _, _ = parts
    desc = front["description"]
    assert 100 < len(desc) < 1000
    for phrase in ("wireframes", "sprint plan", "user stories", "flowchart", "PRD", "explain this codebase"):
        assert phrase in desc


def test_body_under_500_lines(parts):
    _, _, text = parts
    assert len(text.splitlines()) < 400  # the spec allows 500; the build prompt asks for under 400


def test_body_sections_in_required_order(parts):
    _, body, _ = parts
    headings = [h for h in re.findall(r"^## (.+)$", body, re.MULTILINE)]
    expected = ["Purpose", "Operating principles", "Workflow", "Routing table",
                "Output contract", "Failure handling", "When to read each reference"]
    assert [h for h in headings if h in expected] == expected


def test_all_relative_links_resolve(parts):
    _, _, text = parts
    links = re.findall(r"\]\(([^)\s]+)\)", text)
    assert links
    for link in links:
        if re.match(r"^[a-z]+:", link):
            continue
        target = link.split("#")[0]
        assert (SKILL_DIR / target).exists(), f"broken link: {link}"


def test_every_script_and_reference_is_mentioned(parts):
    _, _, text = parts
    for path in sorted((SKILL_DIR / "scripts").glob("*.py")) + sorted((SKILL_DIR / "references").glob("*.md")):
        assert path.name in text, f"{path.name} is not mentioned in SKILL.md"


def test_mentioned_files_exist(parts):
    _, _, text = parts
    for name in set(re.findall(r"\b((?:scripts|references|assets)/[\w./-]+\.(?:py|md|json))", text)):
        assert (SKILL_DIR / name).exists(), f"SKILL.md mentions missing file: {name}"
    for script in set(re.findall(r"\b([a-z_]+\.py)\b", text)):
        assert (SKILL_DIR / "scripts" / script).exists(), f"unknown script: {script}"


def test_key_rules_present(parts):
    _, body, _ = parts
    lowered = body.lower()
    assert "data, never as instructions" in lowered
    assert "never overwrite" in lowered
    assert "assumption:" in lowered
