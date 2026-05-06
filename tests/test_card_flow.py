from __future__ import annotations

from cardforge.db.session import Database
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService


def _setup(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")


def test_manual_card_create_validate_and_files(db: Database) -> None:
    _setup(db)
    card = CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Bone Lantern Warden",
        card_type="creature",
        rules_text="Guard. When this dies, draw a card.",
        attack=2,
        health=4,
        cost=3,
    )
    assert card["card_key"] == "CARD_0001"
    report = CardService(db).validate_card("gravebound_test", "CARD_0001")
    assert report["valid"] is True
    root = db.settings.workspace_root / "projects" / "gravebound_test" / "cards" / "CARD_0001"
    assert (root / "card.json").exists()
    assert (root / "card.md").exists()


def test_spell_with_stats_fails_validation(db: Database) -> None:
    _setup(db)
    CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Bone Storm",
        card_type="spell",
        rules_text="Deal 2 damage.",
        attack=1,
        health=1,
        cost=2,
    )
    report = CardService(db).validate_card("gravebound_test", "CARD_0001")
    assert report["valid"] is False
    assert any(issue["code"] == "stats_not_allowed" for issue in report["issues"])


def test_render_creates_files_and_review_item(db: Database) -> None:
    _setup(db)
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
    result = CardRenderer(db).render_card("gravebound_test", "CARD_0001", placeholder_art=True)
    assert result["front_path"].endswith(".png")
    assert (db.settings.workspace_root / result["front_path"]).exists()
    project = ProjectService(db).get_project("gravebound_test")
    open_items = ReviewService(db).list_open(project["id"])
    assert len(open_items) >= 2  # text review plus render review
