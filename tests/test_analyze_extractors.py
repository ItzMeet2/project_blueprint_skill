import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "project-blueprint" / "scripts" / "analyze_project.py"
SAMPLE = ROOT / "examples" / "sample-dotnet-mvc"

spec = importlib.util.spec_from_file_location("analyze_project", SCRIPT)
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)


def run_cli(project, out):
    proc = subprocess.run([sys.executable, str(SCRIPT), str(project), "--out", str(out)],
                          capture_output=True, text=True)
    return proc, out / "analysis.raw.json"


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    proc, path = run_cli(SAMPLE, tmp_path_factory.mktemp("out"))
    assert proc.returncode == 0, proc.stderr
    return json.loads(path.read_text(encoding="utf-8"))


def test_sample_routes(sample):
    routes = {(r["method"], r["path"]) for r in sample["routes"]}
    assert len(sample["routes"]) >= 8
    assert ("POST", "/account/login") in routes
    assert ("GET", "/account/login") in routes
    assert ("POST", "/account/register") in routes
    assert ("GET", "/books") in routes
    assert ("GET", "/books/{id}") in routes
    assert ("POST", "/books/{id}/delete") in routes
    assert ("GET", "/") in routes


def test_sample_route_handlers(sample):
    handlers = {r["handler"] for r in sample["routes"]}
    assert {"AccountController.Login", "BooksController.Create", "HomeController.Index"} <= handlers


def test_sample_screens(sample):
    assert len(sample["screens"]) == 7
    ids = {s["id"] for s in sample["screens"]}
    assert {"account-login", "account-register", "books-index", "books-details",
            "books-create", "home-index"} <= ids
    layouts = [s for s in sample["screens"] if s.get("is_layout")]
    assert [s["id"] for s in layouts] == ["shared-layout"]
    login = next(s for s in sample["screens"] if s["id"] == "account-login")
    assert login["source"] == "Views/Account/Login.cshtml"


def test_sample_entities(sample):
    by_name = {e["name"]: e for e in sample["entities"]}
    assert set(by_name) == {"Book", "User", "Review"}
    book_fields = {f["name"]: f["type"] for f in by_name["Book"]["fields"]}
    assert book_fields == {"Id": "int", "Title": "string", "Author": "string",
                           "Isbn": "string", "Status": "string", "UserId": "int"}
    assert {f["name"] for f in by_name["User"]["fields"]} == {"Id", "Email", "PasswordHash"}
    assert {f["name"] for f in by_name["Review"]["fields"]} == {"Id", "BookId", "Rating", "Text"}
    assert {"to": "User", "kind": "*..1"} in by_name["Book"]["relations"]


def test_everything_marked_inferred(sample):
    for key in ("routes", "screens", "entities"):
        assert all(item["inferred"] is True for item in sample[key])


def test_no_warnings_on_sample(sample):
    assert sample["warnings"] == []


def test_broken_files_do_not_crash(tmp_path):
    proj = tmp_path / "proj"
    (proj / "Controllers").mkdir(parents=True)
    (proj / "Controllers" / "BrokenController.cs").write_bytes(
        b"\xff\xfe\x00 class BrokenController { [HttpGet( public ((( \x00\x01")
    (proj / "Controllers" / "OkController.cs").write_text(
        'class OkController { [HttpGet("ping")] public IActionResult Ping() => Ok(); }',
        encoding="utf-8")
    (proj / "Models").mkdir()
    (proj / "Models" / "Weird.cs").write_text("class Weird { { { {", encoding="utf-8")
    proc, path = run_cli(proj, tmp_path / "out")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {"method": "GET", "path": "/ping", "handler": "OkController.Ping",
            "inferred": True} in data["routes"]


def test_failing_extractor_is_logged_not_fatal(tmp_path, monkeypatch):
    def boom(root, files, warnings):
        raise RuntimeError("kaboom")

    def fine(root, files, warnings):
        return {"routes": [{"method": "GET", "path": "/x", "handler": "h", "inferred": True}]}

    monkeypatch.setattr(analyze, "EXTRACTORS", [("boom", boom), ("fine", fine)])
    result = analyze.run_extractors(str(tmp_path), [])
    assert any("boom" in w and "kaboom" in w for w in result["warnings"])
    assert len(result["routes"]) == 1


def test_unreadable_file_logged_as_warning(tmp_path):
    warnings = []
    items = analyze.collect(str(tmp_path), ["missing.cs"], lambda r: True,
                            analyze.parse_aspnet_controller, warnings, "t")
    assert items == []
    assert warnings and "missing.cs" in warnings[0]


def test_express_routes(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "server.js").write_text(
        "app.get('/users', h);\nrouter.post(\"/users/:id\", h);\ncache.get('/nope');\n"
        "app.delete(`/users/:id`, h);\n", encoding="utf-8")
    _, path = run_cli(proj, tmp_path / "out")
    routes = {(r["method"], r["path"]) for r in json.loads(path.read_text(encoding="utf-8"))["routes"]}
    assert routes == {("GET", "/users"), ("POST", "/users/:id"), ("DELETE", "/users/:id")}


def test_flask_and_fastapi_routes(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "app.py").write_text(
        '@app.route("/home")\ndef home(): pass\n\n'
        '@app.route("/save", methods=["POST", "PUT"])\ndef save(): pass\n\n'
        '@router.get("/items")\ndef items(): pass\n', encoding="utf-8")
    _, path = run_cli(proj, tmp_path / "out")
    routes = {(r["method"], r["path"], r["handler"])
              for r in json.loads(path.read_text(encoding="utf-8"))["routes"]}
    assert routes == {("GET", "/home", "home"), ("POST", "/save", "save"),
                      ("PUT", "/save", "save"), ("GET", "/items", "items")}


def test_nextjs_app_and_pages(tmp_path):
    proj = tmp_path / "proj"
    for rel in ("app/page.tsx", "app/dashboard/page.tsx", "app/(auth)/login/page.tsx",
                "app/api/hello/route.ts", "pages/about.js", "pages/_app.js"):
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("export default function P() {}", encoding="utf-8")
    (proj / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}', encoding="utf-8")
    _, path = run_cli(proj, tmp_path / "out")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {s["id"] for s in data["screens"]} == {"home", "dashboard", "login", "about"}
    assert ("ANY", "/api/hello") in {(r["method"], r["path"]) for r in data["routes"]}
    assert ("GET", "/login") in {(r["method"], r["path"]) for r in data["routes"]}


def test_nextjs_not_assumed_without_package(tmp_path):
    proj = tmp_path / "proj"
    (proj / "pages").mkdir(parents=True)
    (proj / "pages" / "about.js").write_text("x", encoding="utf-8")
    _, path = run_cli(proj, tmp_path / "out")
    assert json.loads(path.read_text(encoding="utf-8"))["screens"] == []


def test_typescript_and_python_entities(tmp_path):
    proj = tmp_path / "proj"
    (proj / "types").mkdir(parents=True)
    (proj / "types" / "user.ts").write_text(
        "export interface Todo {\n  id: number;\n  title: string;\n  done?: boolean;\n}\n",
        encoding="utf-8")
    (proj / "models.py").write_text(
        "from pydantic import BaseModel\n\nclass Item(BaseModel):\n    name: str\n    price: float = 0\n\n"
        "class Helper:\n    x: int\n", encoding="utf-8")
    _, path = run_cli(proj, tmp_path / "out")
    ents = {e["name"]: [f["name"] for f in e["fields"]]
            for e in json.loads(path.read_text(encoding="utf-8"))["entities"]}
    assert ents == {"Todo": ["id", "title", "done"], "Item": ["name", "price"]}
