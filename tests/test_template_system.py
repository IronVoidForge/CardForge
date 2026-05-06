from __future__ import annotations

import json

from fastapi.testclient import TestClient
from PIL import Image

from cardforge.db.session import Database
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.sets.set_service import SetService
from cardforge.services.templates.template_service import TemplateService, TemplateValidationError
from cardforge.web.app import create_app


def _create_card(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")
    CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Bone Lantern Warden",
        card_type="creature",
        rules_text="Guard. When this dies, draw a card.",
        attack=2,
        health=4,
        cost=3,
    )


def test_template_registry_syncs_defaults(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    service = TemplateService(db)
    result = service.sync_project_templates("gravebound_test")
    assert "default_creature_front_v1" in result["templates"]
    assert "default_card_back_v1" in result["templates"]
    templates = service.list_templates("gravebound_test")
    assert any(template["template_key"] == "default_creature_front_v1" for template in templates)


def test_invalid_template_is_rejected(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    service = TemplateService(db)
    template = service.get_template("gravebound_test", "default_creature_front_v1")
    template["layers"] = []
    try:
        service.update_template("gravebound_test", "default_creature_front_v1", json.dumps(template))
    except TemplateValidationError as exc:
        assert "missing required" in str(exc).lower() or "non-empty layers" in str(exc).lower()
    else:  # pragma: no cover - explicit safety assertion
        raise AssertionError("invalid template update should fail")


def test_renderer_uses_template_canvas(db: Database) -> None:
    _create_card(db)
    service = TemplateService(db)
    template = service.get_template("gravebound_test", "default_creature_front_v1")
    template["canvas"] = {"width": 500, "height": 700, "bleed": 0, "safe_margin": 40}
    service.update_template("gravebound_test", "default_creature_front_v1", json.dumps(template))
    result = CardRenderer(db).render_card("gravebound_test", "CARD_0001")
    image = Image.open(db.settings.workspace_root / result["front_path"])
    assert image.size == (500, 700)
    assert result["layout_report"]["template_id"] == "default_creature_front_v1"


def test_template_ui_pages(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    client = TestClient(create_app(db))
    library = client.get("/projects/gravebound_test/templates")
    assert library.status_code == 200
    assert "Template studio" in library.text
    detail = client.get("/projects/gravebound_test/templates/default_creature_front_v1")
    assert detail.status_code == 200
    assert "Template JSON" in detail.text
