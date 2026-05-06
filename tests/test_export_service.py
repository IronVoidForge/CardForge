from __future__ import annotations

from cardforge.db.session import Database
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.export.export_service import ExportService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.sets.set_service import SetService


def test_json_csv_markdown_and_png_exports(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")
    CardBatchService(db).generate_simulated_batch("gravebound_test", "SET001", count=1, request_text="one card")
    art = ArtCandidateService(db)
    created = art.generate_dummy_candidates("gravebound_test", "CARD_0001", count=1)
    art.approve("gravebound_test", created["candidate_keys"][0])
    art.lock("gravebound_test", created["candidate_keys"][0])
    CardRenderer(db).render_card("gravebound_test", "CARD_0001", placeholder_art=False)

    service = ExportService(db)
    json_export = service.export_json("gravebound_test", "SET001")
    csv_export = service.export_csv("gravebound_test", "SET001")
    md_export = service.export_markdown_catalog("gravebound_test", "SET001")
    png_export = service.export_png_bundle("gravebound_test", "SET001")

    for result in (json_export, csv_export, md_export):
        assert (db.settings.workspace_root / result["output_path"]).exists()
        assert result["card_count"] == 1
    assert (db.settings.workspace_root / png_export["output_path"] / "EXPORT_MANIFEST.json").exists()
    assert png_export["copied_card_count"] == 1
