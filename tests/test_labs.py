from __future__ import annotations

from fastapi.testclient import TestClient

from cardforge.db.session import Database
from cardforge.domain.enums import JobType
from cardforge.services.cards.card_service import CardService
from cardforge.services.jobs.job_service import JobService
from cardforge.services.labs.image_lab_service import ImageLabService
from cardforge.services.labs.prompt_lab_service import PromptLabCaseSpec, PromptLabService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService
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


def test_prompt_lab_case_run_compare_and_promotion_note(db: Database) -> None:
    _setup_card(db)
    service = PromptLabService(db)
    case = service.create_case(
        PromptLabCaseSpec(
            project_slug="gravebound_test",
            template_key="card_refinement_v1",
            target_type="card",
            target_id="CARD_0001",
            notes="Try a shorter refinement contract.",
        )
    )
    assert case["case_key"] == "PLAB_0001"
    run = service.run_case("gravebound_test", "PLAB_0001", variant_notes="Prefer terse rules text.")
    assert run["run_key"] == "RUN_0001"
    assert run["metrics"]["parse_status"] == "parsed"
    comparison = service.compare_runs("gravebound_test", "PLAB_0001")
    assert comparison["run_count"] == 1
    service.mark_run("gravebound_test", "PLAB_0001", "RUN_0001", status="accepted", notes="Better shorter contract.")
    note = service.write_promotion_note("gravebound_test", "PLAB_0001")
    assert (db.settings.workspace_root / note["promotion_note_path"]).exists()


def test_image_lab_attempt_review_compare_and_recommendation(db: Database) -> None:
    _setup_card(db)
    service = ImageLabService(db)
    case = service.create_case("gravebound_test", "CARD_0001", notes="Compare blue grave mist composition.")
    assert case["case_key"] == "ILAB_0001"
    attempt = service.run_attempt("gravebound_test", "ILAB_0001", prompt_append="blue grave mist, centered subject", count=2, seed=123)
    assert attempt["candidate_count"] == 2
    service.review_candidate(
        "gravebound_test",
        "ILAB_0001",
        "ATT_0001",
        "LAB_CAND_001",
        decision="accepted",
        rating=5,
        success_tags=["readable_silhouette"],
    )
    comparison = service.compare_attempts("gravebound_test", "ILAB_0001")
    assert comparison["attempts"][0]["best_rating"] == 5
    recommendation = service.write_recommendation("gravebound_test", "ILAB_0001", notes="Promote blue mist wording.")
    assert (db.settings.workspace_root / recommendation["recommendation_path"]).exists()


def test_lab_jobs_and_web_page(db: Database) -> None:
    _setup_card(db)
    PromptLabService(db).create_case(
        PromptLabCaseSpec(project_slug="gravebound_test", template_key="card_batch_generation_v1", target_type="set", target_id="SET001")
    )
    ImageLabService(db).create_case("gravebound_test", "CARD_0001")
    JobService(db).enqueue(
        "gravebound_test",
        job_type=JobType.PROMPT_LAB_RUN,
        target_type="prompt_lab_case",
        target_id="PLAB_0001",
        payload={"case_key": "PLAB_0001", "variant_notes": "Prefer lower complexity."},
    )
    JobService(db).enqueue(
        "gravebound_test",
        job_type=JobType.IMAGE_LAB_RUN,
        target_type="image_lab_case",
        target_id="ILAB_0001",
        payload={"case_key": "ILAB_0001", "count": 1},
    )
    result = JobService(db).run_all("gravebound_test", limit=2)
    assert result["ran_count"] == 2
    with TestClient(create_app(db)) as client:
        page = client.get("/projects/gravebound_test/labs")
        assert page.status_code == 200
        assert "Prompt Lab & Image Lab" in page.text
        assert "PLAB_0001" in page.text
        assert "ILAB_0001" in page.text
