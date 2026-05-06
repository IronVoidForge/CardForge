from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cardforge.db.schema import migrate
from cardforge.db.session import Database
from cardforge.domain.enums import JobType, ReviewDecision
from cardforge.files.asset_store import AssetStore
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.export.export_service import ExportService
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService
from cardforge.services.jobs.job_service import JobService
from cardforge.services.observability.diagnostics_service import DiagnosticsService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.resume.resume_service import ResumeService
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.auto_review_service import AutoReviewService
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService
from cardforge.services.templates.template_service import TemplateService, TemplateValidationError
from cardforge.services.ui.dashboard_service import UIDashboardService

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"


def create_app(db: Database | None = None) -> FastAPI:
    database = db or Database()
    with database.connection() as conn:
        migrate(conn)
    asset_store = AssetStore(database.settings)
    asset_store.ensure_workspace()

    app = FastAPI(title="CardForge", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATE_DIR)

    def asset_url(path: str | None) -> str:
        value = str(path or "").strip()
        return f"/assets/{value}" if value else ""

    def status_class(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized in {"validated", "approved", "locked", "rendered", "completed", "ok"}:
            return "good"
        if normalized in {"needs-rework", "validation-failed", "layout-warning", "rejected", "failed"}:
            return "bad"
        if normalized in {"open", "generated", "draft", "unreviewed"}:
            return "warn"
        return "neutral"

    templates.env.filters["asset_url"] = asset_url
    templates.env.filters["status_class"] = status_class

    ui = UIDashboardService(database)


    @app.get("/healthz")
    def healthz() -> JSONResponse:
        payload = DiagnosticsService(database).check()
        return JSONResponse(payload, status_code=200 if payload["ok"] else 503)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        projects = ProjectService(database).list_projects()
        return templates.TemplateResponse(request, "home.html", {"projects": projects})

    @app.post("/projects/create")
    def create_project(slug: str = Form(...), name: str = Form(""), description: str = Form("")) -> RedirectResponse:
        ProjectService(database).create_project(slug, name=name, description=description)
        return _redirect(f"/projects/{slug}")

    @app.get("/projects/{project_slug}", response_class=HTMLResponse)
    def project_dashboard(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.project_overview(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "project_dashboard.html", payload)

    @app.post("/projects/{project_slug}/sets/create")
    def create_set(project_slug: str, name: str = Form(...), description: str = Form(""), target_card_count: int = Form(0)) -> RedirectResponse:
        row = SetService(database).create_set(project_slug, name=name, description=description, target_card_count=target_card_count)
        return _redirect(f"/projects/{project_slug}/sets/{row['set_code']}")



    @app.get("/projects/{project_slug}/integrations", response_class=HTMLResponse)
    def integrations_page(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.integration_status(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "integrations.html", payload)

    @app.post("/projects/{project_slug}/integrations/comfy/sync-workflows")
    def sync_comfy_workflows(project_slug: str) -> RedirectResponse:
        WorkflowRegistryService(database).sync_defaults()
        return _redirect(f"/projects/{project_slug}/integrations")


    @app.get("/projects/{project_slug}/jobs", response_class=HTMLResponse)
    def job_queue(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.job_queue(project_slug)
            payload["resume_plan"] = ResumeService(database).plan_project(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "jobs.html", payload)

    @app.post("/projects/{project_slug}/jobs/run-next")
    def run_next_job(project_slug: str) -> RedirectResponse:
        JobService(database).run_next(project_slug)
        return _redirect(f"/projects/{project_slug}/jobs")

    @app.post("/projects/{project_slug}/jobs/run-all")
    def run_all_jobs(project_slug: str) -> RedirectResponse:
        JobService(database).run_all(project_slug, limit=20)
        return _redirect(f"/projects/{project_slug}/jobs")

    @app.post("/projects/{project_slug}/jobs/{job_id}/retry")
    def retry_job(project_slug: str, job_id: int) -> RedirectResponse:
        JobService(database).retry(project_slug, job_id)
        return _redirect(f"/projects/{project_slug}/jobs")

    @app.post("/projects/{project_slug}/jobs/enqueue-next")
    def enqueue_next_job(project_slug: str) -> RedirectResponse:
        plan = ResumeService(database).plan_project(project_slug)
        suggested = plan.get("suggested_jobs", [])
        if suggested:
            first = suggested[0]
            JobService(database).enqueue(
                project_slug,
                job_type=JobType(first["job_type"]),
                target_type=first["target_type"],
                target_id=first["target_id"],
                payload=first.get("payload", {}),
            )
        return _redirect(f"/projects/{project_slug}/jobs")


    @app.get("/projects/{project_slug}/templates", response_class=HTMLResponse)
    def template_library(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.template_library(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "template_library.html", payload)

    @app.post("/projects/{project_slug}/templates/sync")
    def sync_templates(project_slug: str) -> RedirectResponse:
        TemplateService(database).sync_project_templates(project_slug)
        return _redirect(f"/projects/{project_slug}/templates")

    @app.get("/projects/{project_slug}/templates/{template_key}", response_class=HTMLResponse)
    def template_detail(request: Request, project_slug: str, template_key: str) -> HTMLResponse:
        try:
            payload = ui.template_detail(project_slug, template_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "template_detail.html", payload)

    @app.post("/projects/{project_slug}/templates/{template_key}/preview")
    def template_preview(project_slug: str, template_key: str) -> RedirectResponse:
        TemplateService(database).render_preview(project_slug, template_key)
        return _redirect(f"/projects/{project_slug}/templates/{template_key}")

    @app.post("/projects/{project_slug}/templates/{template_key}/update")
    def template_update(project_slug: str, template_key: str, template_json: str = Form(...)) -> RedirectResponse:
        try:
            TemplateService(database).update_template(project_slug, template_key, template_json)
        except (ValueError, TemplateValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/templates/{template_key}")

    @app.get("/projects/{project_slug}/sets/{set_code}", response_class=HTMLResponse)
    def set_detail(request: Request, project_slug: str, set_code: str) -> HTMLResponse:
        try:
            payload = ui.set_detail(project_slug, set_code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "set_detail.html", payload)

    @app.post("/projects/{project_slug}/sets/{set_code}/batches/generate")
    def generate_batch(
        project_slug: str,
        set_code: str,
        request_text: str = Form("Generate a balanced gothic fantasy card batch."),
        count: int = Form(12),
    ) -> RedirectResponse:
        result = CardBatchService(database).generate_batch(project_slug, set_code, count=count, request_text=request_text, use_mock=True)
        return _redirect(f"/projects/{project_slug}/batches/{result['batch_key']}")

    @app.post("/projects/{project_slug}/sets/{set_code}/cards/create")
    def create_card(
        project_slug: str,
        set_code: str,
        name: str = Form(...),
        card_type: str = Form("creature"),
        rules_text: str = Form(""),
        rarity: str = Form("common"),
        faction: str = Form(""),
        cost: int = Form(0),
        attack: str = Form(""),
        health: str = Form(""),
        art_direction: str = Form(""),
    ) -> RedirectResponse:
        card = CardService(database).create_card(
            project_slug,
            set_code,
            name=name,
            card_type=card_type,
            rarity=rarity,
            faction=faction,
            rules_text=rules_text,
            cost=cost,
            attack=_optional_int(attack),
            health=_optional_int(health),
            art_direction=art_direction,
        )
        return _redirect(f"/projects/{project_slug}/cards/{card['card_key']}")


    @app.post("/projects/{project_slug}/sets/{set_code}/export/{export_type}")
    def export_set(project_slug: str, set_code: str, export_type: str) -> RedirectResponse:
        service = ExportService(database)
        if export_type == "json":
            service.export_json(project_slug, set_code)
        elif export_type == "csv":
            service.export_csv(project_slug, set_code)
        elif export_type == "markdown":
            service.export_markdown_catalog(project_slug, set_code)
        elif export_type == "png":
            service.export_png_bundle(project_slug, set_code)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported export type: {export_type}")
        return _redirect(f"/projects/{project_slug}/sets/{set_code}")

    @app.get("/projects/{project_slug}/batches/{batch_key}", response_class=HTMLResponse)
    def batch_detail(request: Request, project_slug: str, batch_key: str) -> HTMLResponse:
        try:
            payload = ui.batch_detail(project_slug, batch_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "batch_detail.html", payload)

    @app.post("/projects/{project_slug}/batches/{batch_key}/auto-review")
    def auto_review_batch(project_slug: str, batch_key: str) -> RedirectResponse:
        AutoReviewService(database).review_batch_text(project_slug, batch_key)
        return _redirect(f"/projects/{project_slug}/batches/{batch_key}")

    @app.post("/projects/{project_slug}/batches/{batch_key}/validate")
    def validate_batch(project_slug: str, batch_key: str) -> RedirectResponse:
        CardBatchService(database).validate_batch(project_slug, batch_key)
        return _redirect(f"/projects/{project_slug}/batches/{batch_key}")

    @app.get("/projects/{project_slug}/cards/{card_key}", response_class=HTMLResponse)
    def card_detail(request: Request, project_slug: str, card_key: str) -> HTMLResponse:
        try:
            payload = ui.card_detail(project_slug, card_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "card_detail.html", payload)

    @app.post("/projects/{project_slug}/cards/{card_key}/edit")
    def edit_card(
        project_slug: str,
        card_key: str,
        name: str = Form(...),
        type_line: str = Form(""),
        rarity: str = Form("common"),
        faction: str = Form(""),
        rules_text: str = Form(""),
        flavor_text: str = Form(""),
        design_notes: str = Form(""),
        art_direction: str = Form(""),
    ) -> RedirectResponse:
        CardService(database).update_card_fields(
            project_slug,
            card_key,
            source="ui_edit",
            change_reason="Edited from CardForge UI",
            name=name,
            type_line=type_line,
            rarity=rarity,
            faction=faction,
            rules_text=rules_text,
            flavor_text=flavor_text,
            design_notes=design_notes,
            art_direction=art_direction,
        )
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/validate")
    def validate_card(project_slug: str, card_key: str) -> RedirectResponse:
        CardService(database).validate_card(project_slug, card_key)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/autofill")
    def autofill_card(project_slug: str, card_key: str) -> RedirectResponse:
        CardAutofillService(database).autofill_card(project_slug, card_key)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/refine")
    def refine_card(project_slug: str, card_key: str) -> RedirectResponse:
        CardRefinementService(database).refine_card(project_slug, card_key)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/auto-review")
    def auto_review_card(project_slug: str, card_key: str) -> RedirectResponse:
        AutoReviewService(database).review_card_text(project_slug, card_key)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")


    @app.post("/projects/{project_slug}/cards/{card_key}/art/prepare-comfy")
    def prepare_comfy_art(project_slug: str, card_key: str, workflow_key: str = Form("stub.card_art.t2i.v1")) -> RedirectResponse:
        ComfyArtService(database).prepare_card_art(project_slug, card_key, workflow_key=workflow_key, submit=False)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/art/generate-dummy")
    def generate_dummy_art(project_slug: str, card_key: str, count: int = Form(4)) -> RedirectResponse:
        ArtCandidateService(database).generate_dummy_candidates(project_slug, card_key, count=count)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/art/{candidate_key}/approve")
    def approve_art(project_slug: str, candidate_key: str, card_key: str = Form("")) -> RedirectResponse:
        ArtCandidateService(database).approve(project_slug, candidate_key)
        return _redirect(_card_or_project_path(project_slug, card_key))

    @app.post("/projects/{project_slug}/art/{candidate_key}/lock")
    def lock_art(project_slug: str, candidate_key: str, card_key: str = Form("")) -> RedirectResponse:
        ArtCandidateService(database).lock(project_slug, candidate_key)
        return _redirect(_card_or_project_path(project_slug, card_key))

    @app.post("/projects/{project_slug}/art/{candidate_key}/reject")
    def reject_art(project_slug: str, candidate_key: str, reason: str = Form("Rejected from UI"), card_key: str = Form("")) -> RedirectResponse:
        ArtCandidateService(database).reject(project_slug, candidate_key, reason=reason)
        return _redirect(_card_or_project_path(project_slug, card_key))

    @app.post("/projects/{project_slug}/art/{candidate_key}/auto-review")
    def auto_review_art(project_slug: str, candidate_key: str, card_key: str = Form("")) -> RedirectResponse:
        AutoReviewService(database).review_art_candidate(project_slug, candidate_key)
        return _redirect(_card_or_project_path(project_slug, card_key))

    @app.post("/projects/{project_slug}/cards/{card_key}/render")
    def render_card(project_slug: str, card_key: str, placeholder_art: str = Form("yes")) -> RedirectResponse:
        CardRenderer(database).render_card(project_slug, card_key, placeholder_art=placeholder_art == "yes")
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.get("/projects/{project_slug}/review", response_class=HTMLResponse)
    def review_queue(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.review_queue(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "review_queue.html", payload)

    @app.post("/projects/{project_slug}/review/{review_id}/decide")
    def decide_review(
        project_slug: str,
        review_id: int,
        decision: str = Form(...),
        reason: str = Form(""),
        notes: str = Form(""),
    ) -> RedirectResponse:
        try:
            decision_enum = ReviewDecision(decision)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsupported decision: {decision}") from exc
        ReviewService(database).decide(review_id, decision=decision_enum, reason=reason, notes=notes)
        return _redirect(f"/projects/{project_slug}/review")

    @app.get("/assets/{asset_path:path}")
    def assets(asset_path: str) -> FileResponse:
        try:
            path = asset_store.safe_resolve(asset_path)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(path)

    return app


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _optional_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _card_or_project_path(project_slug: str, card_key: str) -> str:
    return f"/projects/{project_slug}/cards/{card_key}" if card_key else f"/projects/{project_slug}"


app = create_app()
