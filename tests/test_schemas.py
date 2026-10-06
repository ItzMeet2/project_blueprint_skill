import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ASSETS = Path(__file__).resolve().parent.parent / "project-blueprint" / "assets"
PROFILE_SCHEMA = ASSETS / "schemas" / "profile.schema.json"
WIREFRAME_SCHEMA = ASSETS / "schemas" / "wireframe.schema.json"
PROFILE_EXAMPLE = ASSETS / "schemas" / "examples" / "profile.example.json"
WIREFRAME_EXAMPLE = ASSETS / "templates" / "wireframe-spec.example.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def profile_validator():
    schema = load(PROFILE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def wireframe_validator():
    schema = load(WIREFRAME_SCHEMA)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_profile_example_valid(profile_validator):
    assert list(profile_validator.iter_errors(load(PROFILE_EXAMPLE))) == []


def test_wireframe_example_valid(wireframe_validator):
    assert list(wireframe_validator.iter_errors(load(WIREFRAME_EXAMPLE))) == []


def test_wireframe_example_has_three_linked_screens():
    spec = load(WIREFRAME_EXAMPLE)
    ids = {s["id"] for s in spec["screens"]}
    assert len(spec["screens"]) == 3
    for screen in spec["screens"]:
        for nav in screen["navigates_to"]:
            assert nav["screen"] in ids


def test_profile_missing_required_field(profile_validator):
    doc = load(PROFILE_EXAMPLE)
    del doc["project"]["name"]
    assert list(profile_validator.iter_errors(doc))


def test_profile_bad_screen_id(profile_validator):
    doc = load(PROFILE_EXAMPLE)
    doc["screens"][0]["id"] = "Account_Login"
    assert list(profile_validator.iter_errors(doc))


def test_profile_bad_project_type(profile_validator):
    doc = load(PROFILE_EXAMPLE)
    doc["project"]["type"] = "spaceship"
    assert list(profile_validator.iter_errors(doc))


def test_profile_unknown_top_level_key(profile_validator):
    doc = load(PROFILE_EXAMPLE)
    doc["surprise"] = 1
    assert list(profile_validator.iter_errors(doc))


def test_wireframe_unknown_element_type(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["elements"].append({"type": "hologram", "text": "x"})
    assert list(wireframe_validator.iter_errors(doc))


def test_wireframe_button_requires_text(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["elements"] = [{"type": "button"}]
    assert list(wireframe_validator.iter_errors(doc))


def test_wireframe_input_requires_label(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["elements"] = [{"type": "input", "placeholder": "x"}]
    assert list(wireframe_validator.iter_errors(doc))


def test_wireframe_bad_screen_id(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["id"] = "Bad Id"
    assert list(wireframe_validator.iter_errors(doc))


def test_wireframe_state_variant_id_allowed(wireframe_validator):
    doc = copy.deepcopy(load(WIREFRAME_EXAMPLE))
    doc["screens"][1]["id"] = "dashboard--empty"
    assert list(wireframe_validator.iter_errors(doc)) == []


def test_wireframe_nested_children_validated(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["elements"] = [
        {"type": "row", "children": [{"type": "column", "children": [{"type": "button"}]}]}
    ]
    assert list(wireframe_validator.iter_errors(doc))


def test_wireframe_nested_children_valid(wireframe_validator):
    doc = load(WIREFRAME_EXAMPLE)
    doc["screens"][0]["elements"] = [
        {"type": "row", "children": [{"type": "column", "children": [{"type": "button", "text": "Go"}]}]}
    ]
    assert list(wireframe_validator.iter_errors(doc)) == []
