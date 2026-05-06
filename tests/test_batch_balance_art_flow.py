from __future__ import annotations

from cardforge.db.session import Database
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.balance.balance_review_service import BalanceReviewService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.rework.card_rework_service import CardReworkService
from cardforge.services.sets.set_service import SetService


def _setup(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")


def test_simulated_batch_generation_validates_and_writes_files(db: Database) -> None:
    _setup(db)
    result = CardBatchService(db).generate_simulated_batch(
        "gravebound_test",
        "SET001",
        count=12,
        request_text="Generate gothic necromancer cards.",
    )
    assert result["created_card_count"] == 12
    assert result["batch_key"] == "BATCH_0001"
    root = db.settings.workspace_root / "projects" / "gravebound_test"
    assert (root / "batches" / "BATCH_0001" / "raw_response.md").exists()
    assert (root / "cards" / "CARD_0001" / "card.md").exists()


def test_balance_review_and_repair(db: Database) -> None:
    _setup(db)
    CardBatchService(db).generate_simulated_batch("gravebound_test", "SET001", count=4, request_text="small batch")
    balance = BalanceReviewService(db).review_batch("gravebound_test", "BATCH_0001")
    assert balance["card_count"] == 4
    assert balance["cost_curve"]
    repaired = CardReworkService(db).repair_rules_text("gravebound_test", "CARD_0001", reason="shorten for template")
    assert repaired["new_version_id"]
    assert "Reworked" in repaired["rules_text"]


def test_dummy_art_candidate_lock_and_render_with_locked_art(db: Database) -> None:
    _setup(db)
    CardBatchService(db).generate_simulated_batch("gravebound_test", "SET001", count=1, request_text="one card")
    art_service = ArtCandidateService(db)
    generated = art_service.generate_dummy_candidates("gravebound_test", "CARD_0001", count=2)
    candidate_key = generated["candidate_keys"][0]
    art_service.approve_candidate("gravebound_test", candidate_key)
    locked = art_service.lock_candidate("gravebound_test", candidate_key)
    assert locked["locked_art_path"].endswith("locked_art.png")
    render = CardRenderer(db).render_card("gravebound_test", "CARD_0001", placeholder_art=False)
    assert (db.settings.workspace_root / render["front_path"]).exists()
    assert render["status"] in {"rendered", "layout_warning"}
