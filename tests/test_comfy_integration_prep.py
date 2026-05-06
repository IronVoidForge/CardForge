from __future__ import annotations

import json

from fastapi.testclient import TestClient

from cardforge.db.session import Database
from cardforge.domain.enums import JobType
from cardforge.services.cards.card_service import CardService
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService
from cardforge.services.jobs.job_service import JobService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService
from cardforge.web.app import create_app


def _project_with_card(db: Database) -> None:
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
        art_direction="A skeletal warden holding a bone lantern in violet fog.",
    )


def test_workflow_registry_sync_and_validate(db: Database) -> None:
    service = WorkflowRegistryService(db)
    sync = service.sync_defaults()
    assert "stub.card_art.t2i.v1" in sync["workflow_keys"]
    workflows = service.list_workflows()
    assert workflows[0]["workflow_key"] == "stub.card_art.t2i.v1"
    validation = service.validate_workflow("stub.card_art.t2i.v1")
    assert validation["valid"] is True
    assert (db.settings.workspace_root / validation["workflow_path"]).exists()


def test_prepare_comfy_art_writes_patched_workflow_without_live_comfy(db: Database) -> None:
    _project_with_card(db)
    result = ComfyArtService(db).prepare_card_art("gravebound_test", "CARD_0001", seed=123, submit=False)
    assert result["status"] == "prepared"
    patched_path = db.settings.workspace_root / result["patched_workflow_path"]
    manifest_path = db.settings.workspace_root / result["manifest_path"]
    assert patched_path.exists()
    assert manifest_path.exists()
    payload = json.loads(patched_path.read_text(encoding="utf-8"))
    assert payload["3"]["inputs"]["seed"] == 123
    assert "Bone Lantern" in payload["6"]["inputs"]["text"] or "skeletal" in payload["6"]["inputs"]["text"].lower()
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM comfy_jobs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "prepared"
    assert row["patched_workflow_path"] == result["patched_workflow_path"]


def test_job_dispatcher_can_prepare_comfy_art(db: Database) -> None:
    _project_with_card(db)
    job = JobService(db).enqueue(
        "gravebound_test",
        job_type=JobType.ART_PREPARE_COMFY,
        target_type="card",
        target_id="CARD_0001",
        payload={"card_key": "CARD_0001", "seed": 555},
    )
    assert job["status"] == "pending"
    result = JobService(db).run_next("gravebound_test")
    assert result is not None
    assert result.status.value == "completed"
    assert result.result["status"] == "prepared"


def test_integration_ui_page_lists_workflows(db: Database) -> None:
    _project_with_card(db)
    WorkflowRegistryService(db).sync_defaults()
    client = TestClient(create_app(db))
    response = client.get("/projects/gravebound_test/integrations")
    assert response.status_code == 200
    assert "LM Studio and ComfyUI" in response.text
    assert "stub.card_art.t2i.v1" in response.text
