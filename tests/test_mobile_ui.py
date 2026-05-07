from __future__ import annotations

from fastapi.testclient import TestClient

from cardforge.db.schema import migrate
from cardforge.db.session import Database
from cardforge.services.mobile.mobile_launcher import mobile_url, write_mobile_launcher
from cardforge.services.projects.project_service import ProjectService
from cardforge.web.app import create_app


def test_mobile_manifest_and_routes_without_auth(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    with TestClient(create_app(db)) as client:
        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert manifest.json()["start_url"] == "/m"
        shell = client.get("/service-worker.js")
        assert shell.status_code == 200
        assert "cardforge-mobile-shell" in shell.text
        mobile = client.get("/m/gravebound_test")
        assert mobile.status_code == 200
        assert "CardForge Mobile" in mobile.text or "Quick actions" in mobile.text


def test_mobile_auth_login_and_csrf(workspace, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CARDFORGE_UI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("CARDFORGE_UI_PASSWORD", "secret")
    monkeypatch.setenv("CARDFORGE_UI_SESSION_SECRET", "test-secret")
    db = Database()
    with db.connection() as conn:
        migrate(conn)
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    with TestClient(create_app(db), follow_redirects=False) as client:
        blocked = client.get("/m/gravebound_test")
        assert blocked.status_code == 303
        assert blocked.headers["location"].startswith("/login")

        bad = client.post("/login", data={"password": "wrong", "next": "/m/gravebound_test"})
        assert bad.status_code == 303
        assert bad.headers["location"].startswith("/login")

        login = client.post("/login", data={"password": "secret", "next": "/m/gravebound_test"})
        assert login.status_code == 303
        assert login.headers["location"] == "/m/gravebound_test"
        csrf = client.cookies.get("cardforge_csrf")
        assert csrf

        mobile = client.get("/m/gravebound_test")
        assert mobile.status_code == 200
        assert "Quick actions" in mobile.text

        forbidden = client.post("/projects/gravebound_test/sets/create", data={"name": "No Token"})
        assert forbidden.status_code == 403

        created = client.post(
            "/projects/gravebound_test/sets/create",
            data={"name": "With Token", "csrf_token": csrf},
        )
        assert created.status_code == 303
        assert created.headers["location"].endswith("/projects/gravebound_test/sets/SET001")


def test_mobile_launcher_file(db: Database, tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = mobile_url(host="192.168.1.50", port=8765)
    result = write_mobile_launcher(url, settings=db.settings, output=tmp_path / "launcher.html")
    assert result.path.exists()
    text = result.path.read_text(encoding="utf-8")
    assert url in text
    assert "Opening CardForge Mobile" in text
