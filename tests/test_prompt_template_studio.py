from __future__ import annotations

from fastapi.testclient import TestClient

from cardforge.db.session import Database
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_template_studio import PromptTemplateStudioService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService
from cardforge.web.app import create_app


def test_prompt_studio_manual_proposal_edit_approve_activate(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    PromptTemplateVersionService(db).sync_project("gravebound_test")
    studio = PromptTemplateStudioService(db)
    proposal = studio.create_manual_proposal(
        "gravebound_test",
        template_key="card_refinement_v1",
        summary="Try a stronger concise rules instruction.",
    )
    assert proposal["version_key"] == "card_refinement_v1_v002"
    detail = studio.version_detail("gravebound_test", "card_refinement_v1_v002")
    assert detail["editable"] is True
    assert detail["diff_lines"] == []

    updated_markdown = detail["selected_markdown"].rstrip() + "\n\n# Studio Note\nPrefer rules text under two lines.\n"
    saved = studio.update_version_markdown(
        "gravebound_test",
        "card_refinement_v1_v002",
        markdown=updated_markdown,
        summary="Added a two-line rules preference.",
    )
    assert saved["status"] == "proposed"
    detail = studio.version_detail("gravebound_test", "card_refinement_v1_v002")
    assert any(line["kind"] == "add" and "Studio Note" in line["text"] for line in detail["diff_lines"])

    PromptTemplateVersionService(db).approve_version("gravebound_test", "card_refinement_v1_v002")
    PromptTemplateVersionService(db).activate_version("gravebound_test", "card_refinement_v1_v002")
    active = PromptTemplateVersionService(db).get_active_template_markdown("gravebound_test", "card_refinement_v1")
    assert "Prefer rules text under two lines." in active


def test_prompt_studio_web_pages(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    with TestClient(create_app(db), follow_redirects=False) as client:
        dashboard = client.get("/projects/gravebound_test/prompt-studio")
        assert dashboard.status_code == 200
        assert "Prompt Template Studio" in dashboard.text
        proposed = client.post(
            "/projects/gravebound_test/prompt-studio/card_refinement_v1/propose",
            data={"summary": "Manual web proposal."},
        )
        assert proposed.status_code == 303
        assert proposed.headers["location"].endswith("/projects/gravebound_test/prompt-studio/card_refinement_v1_v002")
        detail = client.get("/projects/gravebound_test/prompt-studio/card_refinement_v1_v002")
        assert detail.status_code == 200
        assert "Diff against active" in detail.text
        assert "Validate and save proposed version" in detail.text
