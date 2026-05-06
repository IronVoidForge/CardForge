from __future__ import annotations

from fastapi.testclient import TestClient

from cardforge.db.session import Database
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService
from cardforge.web.app import create_app


def _client(db: Database) -> TestClient:
    return TestClient(create_app(db))


def test_web_home_and_project_dashboard(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    client = _client(db)
    home = client.get("/")
    assert home.status_code == 200
    assert "Gravebound Test" in home.text
    dashboard = client.get("/projects/gravebound_test")
    assert dashboard.status_code == 200
    assert "Next best action" in dashboard.text
    assert "Create set" in dashboard.text


def test_web_offline_generation_card_render_and_review_flow(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")
    client = _client(db)

    generated = client.post(
        "/projects/gravebound_test/sets/SET001/batches/generate",
        data={"count": "3", "request_text": "Generate gothic necromancer cards."},
        follow_redirects=False,
    )
    assert generated.status_code == 303
    assert generated.headers["location"].endswith("/projects/gravebound_test/batches/BATCH_0001")

    batch_page = client.get("/projects/gravebound_test/batches/BATCH_0001")
    assert batch_page.status_code == 200
    assert "Cards in batch" in batch_page.text
    assert "CARD_0001" in batch_page.text

    card_page = client.get("/projects/gravebound_test/cards/CARD_0001")
    assert card_page.status_code == 200
    assert "Offline AI helpers" in card_page.text

    client.post("/projects/gravebound_test/cards/CARD_0001/art/generate-dummy", data={"count": "1"})
    client.post("/projects/gravebound_test/art/ART_CAND_0001/approve", data={"card_key": "CARD_0001"})
    client.post("/projects/gravebound_test/art/ART_CAND_0001/lock", data={"card_key": "CARD_0001"})
    rendered = client.post(
        "/projects/gravebound_test/cards/CARD_0001/render",
        data={"placeholder_art": "no"},
        follow_redirects=False,
    )
    assert rendered.status_code == 303

    card_page = client.get("/projects/gravebound_test/cards/CARD_0001")
    assert "RENDER_0001" in card_page.text
    assert "locked" in card_page.text

    exported = client.post("/projects/gravebound_test/sets/SET001/export/json", follow_redirects=False)
    assert exported.status_code == 303
    assert (db.settings.workspace_root / "projects" / "gravebound_test" / "exports" / "json" / "set001_cards.json").exists()

    review_page = client.get("/projects/gravebound_test/review")
    assert review_page.status_code == 200
    assert "Review queue" in review_page.text
