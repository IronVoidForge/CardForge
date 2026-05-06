from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cardforge.db.session import Database
from cardforge.services.cards.card_service import CardService
from cardforge.services.labs.image_lab_service import ImageLabService
from cardforge.services.labs.lab_promotion_service import LabPromotionService
from cardforge.services.labs.prompt_lab_service import PromptLabCaseSpec, PromptLabService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService
from cardforge.services.sets.set_service import SetService
from cardforge.services.ui.dashboard_service import UIDashboardService
from cardforge.web.app import create_app


def _setup_card(db: Database) -> None:
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


def _accepted_prompt_lab_run(db: Database) -> tuple[str, str]:
    service = PromptLabService(db)
    service.create_case(
        PromptLabCaseSpec(
            project_slug="gravebound_test",
            template_key="card_refinement_v1",
            target_type="card",
            target_id="CARD_0001",
            notes="Try shorter refinements.",
        )
    )
    service.run_case("gravebound_test", "PLAB_0001", variant_notes="Prefer two-line rules text.")
    service.mark_run("gravebound_test", "PLAB_0001", "RUN_0001", status="accepted", notes="Good short contract.")
    return "PLAB_0001", "RUN_0001"


def test_prompt_template_sync_seeds_versions(db: Database) -> None:
    _setup_card(db)
    result = PromptTemplateVersionService(db).sync_project("gravebound_test")
    assert result["synced_count"] >= 1
    versions = PromptTemplateVersionService(db).list_versions("gravebound_test", "card_refinement_v1")
    assert versions
    assert versions[-1]["version_key"] == "card_refinement_v1_v001"
    assert versions[-1]["status"] == "active"


def test_lab_promotion_requires_accepted_run(db: Database) -> None:
    _setup_card(db)
    PromptLabService(db).create_case(
        PromptLabCaseSpec(project_slug="gravebound_test", template_key="card_refinement_v1", target_type="card", target_id="CARD_0001")
    )
    PromptLabService(db).run_case("gravebound_test", "PLAB_0001")
    with pytest.raises(ValueError, match="accepted"):
        LabPromotionService(db).create_prompt_template_request("gravebound_test", "PLAB_0001", run_key="RUN_0001")


def test_lab_promotion_approve_apply_creates_active_template_version(db: Database) -> None:
    _setup_card(db)
    case_key, run_key = _accepted_prompt_lab_run(db)
    promotion = LabPromotionService(db).create_prompt_template_request("gravebound_test", case_key, run_key=run_key, notes="Keep rules concise.")
    assert promotion["request_key"] == "PROMO_0001"
    LabPromotionService(db).approve_request("gravebound_test", "PROMO_0001", notes="Evidence looks good.")
    applied = LabPromotionService(db).apply_request("gravebound_test", "PROMO_0001")
    assert applied["status"] == "applied"
    assert applied["version_key"] == "card_refinement_v1_v002"
    versions = PromptTemplateVersionService(db).list_versions("gravebound_test", "card_refinement_v1")
    active = [item for item in versions if item["status"] == "active"]
    assert active[0]["version_key"] == "card_refinement_v1_v002"
    active_markdown = PromptTemplateVersionService(db).get_active_template_markdown("gravebound_test", "card_refinement_v1")
    assert "Accepted Prompt Lab Guidance" in active_markdown


def test_image_lab_promotion_request_is_reviewable_but_not_auto_applied(db: Database) -> None:
    _setup_card(db)
    service = ImageLabService(db)
    service.create_case("gravebound_test", "CARD_0001")
    service.run_attempt("gravebound_test", "ILAB_0001", prompt_append="violet rim light", count=1, seed=42)
    service.review_candidate("gravebound_test", "ILAB_0001", "ATT_0001", "LAB_CAND_001", decision="accepted", rating=5)
    promotion = service.propose_art_prompt_update("gravebound_test", "ILAB_0001", notes="Use violet rim light wording.")
    assert promotion["request_key"] == "PROMO_0001"
    requests = LabPromotionService(db).list_requests("gravebound_test")
    assert requests[0]["lab_type"] == "image_lab"
    LabPromotionService(db).approve_request("gravebound_test", "PROMO_0001")
    with pytest.raises(ValueError, match="Prompt Lab"):
        LabPromotionService(db).apply_request("gravebound_test", "PROMO_0001")


def test_lab_dashboard_shows_promotions_and_versions(db: Database) -> None:
    _setup_card(db)
    case_key, run_key = _accepted_prompt_lab_run(db)
    LabPromotionService(db).create_prompt_template_request("gravebound_test", case_key, run_key=run_key)
    dashboard = UIDashboardService(db).lab_dashboard("gravebound_test")
    assert dashboard["promotion_requests"]
    assert dashboard["prompt_versions"]
    assert dashboard["open_promotions"] == 1
    with TestClient(create_app(db)) as client:
        page = client.get("/projects/gravebound_test/labs")
        assert page.status_code == 200
        assert "Prompt template promotion requests" in page.text
        assert "PROMO_0001" in page.text
