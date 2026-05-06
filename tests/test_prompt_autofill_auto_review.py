from __future__ import annotations

from cardforge.db.session import Database
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.review.auto_review_service import AutoReviewService
from cardforge.services.sets.set_service import SetService


def _setup(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")


def test_prompt_templates_are_scaffolded_and_render_prompt_package(db: Database) -> None:
    _setup(db)
    prompt_service = PromptTemplateService(db)
    templates = prompt_service.list_templates("gravebound_test")
    keys = {item["template_key"] for item in templates}
    assert "card_batch_generation_v1" in keys
    package = prompt_service.render_package(
        "gravebound_test",
        template_key="card_autofill_v1",
        task_type="card_autofill",
        context={
            "project_slug": "gravebound_test",
            "card_key": "CARD_0001",
            "name": "Test Card",
            "card_type": "creature",
            "rarity": "common",
            "faction": "Gravebound",
            "missing_fields": ["rules_text"],
            "rules_text": "",
            "flavor_text": "",
            "art_direction": "",
        },
    )
    assert package.package_key == "PROMPT_0001"
    assert "CARDFORGE_PACKET" in package.system_prompt
    assert (db.settings.workspace_root / package.package_markdown_path).exists()


def test_card_autofill_completes_missing_fields_and_logs_prompt(db: Database) -> None:
    _setup(db)
    CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Nameless Grave Guard",
        card_type="creature",
        attack=None,
        health=None,
        cost=2,
    )
    result = CardAutofillService(db).autofill_card("gravebound_test", "CARD_0001")
    assert result["changed"] is True
    assert "rules_text" in result["updated_fields"]
    assert result["prompt_package_key"] == "PROMPT_0001"
    card = CardService(db).get_card("gravebound_test", "CARD_0001")
    assert card["rules_text"]
    assert card["art_direction"]
    assert (db.settings.workspace_root / "projects" / "gravebound_test" / "cards" / "CARD_0001" / "autofill_report.json").exists()


def test_auto_review_and_refinement_reduce_rework_findings(db: Database) -> None:
    _setup(db)
    long_rules = "thing " * 120
    CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Overfull Necromancer",
        card_type="creature",
        rules_text=long_rules,
        attack=1,
        health=3,
        cost=2,
        art_direction="",
    )
    before = AutoReviewService(db).review_card_text("gravebound_test", "CARD_0001")
    assert before["auto_status"] == "needs_rework"
    refined = CardRefinementService(db).refine_card("gravebound_test", "CARD_0001")
    assert refined["changed"] is True
    after = refined["after_review"]
    assert after["score_100"] >= before["score_100"]
    card = CardService(db).get_card("gravebound_test", "CARD_0001")
    assert "thing" not in card["rules_text"]
    assert (db.settings.workspace_root / "projects" / "gravebound_test" / "cards" / "CARD_0001" / "refinement_report.json").exists()


def test_auto_review_art_candidate_stores_score_json(db: Database) -> None:
    _setup(db)
    CardService(db).create_card(
        "gravebound_test",
        "SET001",
        name="Bone Lantern Warden",
        card_type="creature",
        rules_text="Guard.",
        attack=2,
        health=4,
        cost=3,
        art_direction="skeletal guard with violet lantern",
    )
    generated = ArtCandidateService(db).generate_dummy_candidates("gravebound_test", "CARD_0001", count=1)
    report = AutoReviewService(db).review_art_candidate("gravebound_test", generated["candidate_keys"][0])
    assert report["score_100"] >= 80
    with db.connection() as conn:
        row = conn.execute("SELECT score_json FROM art_candidates WHERE candidate_key = ?", (generated["candidate_keys"][0],)).fetchone()
    assert "auto_status" in row["score_json"]
