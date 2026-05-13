from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cardforge.db.schema import migrate
from cardforge.db.session import Database
from cardforge.domain.enums import JobType, ReviewDecision
from cardforge.files.asset_store import AssetStore
from cardforge.integrations.comfyui import ComfyClient
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.export.export_service import ExportService
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService
from cardforge.services.jobs.job_service import JobService
from cardforge.services.integrations.integration_config_service import IntegrationConfigService
from cardforge.services.labs.image_lab_service import ImageLabService
from cardforge.services.labs.lab_promotion_service import LabPromotionService
from cardforge.services.labs.prompt_lab_service import PromptLabCaseSpec, PromptLabService
from cardforge.services.observability.diagnostics_service import DiagnosticsService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.resume.resume_service import ResumeService
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.auto_review_service import AutoReviewService
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService
from cardforge.services.prompts.prompt_template_studio import PromptTemplateStudioService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService
from cardforge.services.templates.template_service import TemplateService, TemplateValidationError
from cardforge.services.ui.dashboard_service import UIDashboardService
from cardforge.web.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    UIAuth,
    login_redirect,
    read_csrf_token,
    safe_redirect_target,
    wants_html,
)

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
    auth = UIAuth(database.settings)

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


    @app.middleware("http")
    async def mobile_operator_security(request: Request, call_next: Any) -> Response:
        request.state.auth_required = auth.required
        request.state.mobile_only = database.settings.ui_mobile_only
        request.state.authenticated = auth.verify_session(request.cookies.get(SESSION_COOKIE))
        request.state.csrf_token = request.cookies.get(CSRF_COOKIE, "")
        if auth.required and not auth.public_path(request.url.path):
            if not request.state.authenticated:
                if wants_html(request):
                    return login_redirect(request)
                return JSONResponse({"ok": False, "error": "Authentication required."}, status_code=401)
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                csrf_token = await read_csrf_token(request)
                if not auth.verify_csrf(csrf_token):
                    return JSONResponse({"ok": False, "error": "Invalid CSRF token."}, status_code=403)
        response = await call_next(request)
        if auth.required and request.state.authenticated:
            auth.ensure_csrf_cookie(request, response)
        return response

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        payload = DiagnosticsService(database).check()
        return JSONResponse(payload, status_code=200 if payload["ok"] else 503)



    @app.get("/manifest.webmanifest")
    def web_manifest() -> JSONResponse:
        return JSONResponse(
            {
                "name": "CardForge Mobile Operator",
                "short_name": "CardForge",
                "description": "Mobile-first operator UI for local card generation pipelines.",
                "start_url": "/m",
                "scope": "/",
                "display": "standalone",
                "background_color": "#f4efe6",
                "theme_color": "#472184",
                "icons": [
                    {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
                ],
            }
        )

    @app.get("/service-worker.js")
    def service_worker() -> Response:
        body = (STATIC_DIR / "service-worker.js").read_text(encoding="utf-8")
        return Response(body, media_type="application/javascript")

    @app.get("/offline", response_class=HTMLResponse)
    def offline(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "offline.html", {})

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/") -> HTMLResponse:  # noqa: A002 - user-facing query name
        if not auth.required:
            return _redirect(safe_redirect_target(next))
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next_url": safe_redirect_target(next), "error": "", "password_configured": auth.password_configured},
        )

    @app.post("/login")
    def login(password: str = Form(""), next: str = Form("/")) -> RedirectResponse:  # noqa: A002
        result = auth.authenticate(password)
        if not result.ok:
            response = _redirect(f"/login?next={safe_redirect_target(next)}")
            response.set_cookie("cardforge_login_error", result.error, max_age=8, samesite="lax")
            return response
        return auth.login_response(next)

    @app.post("/logout")
    def logout() -> RedirectResponse:
        return auth.logout_response()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        if database.settings.ui_mobile_only:
            return _redirect("/m")
        projects = ProjectService(database).list_projects()
        return templates.TemplateResponse(request, "home.html", {"projects": projects})



    @app.get("/m", response_class=HTMLResponse)
    def mobile_home(request: Request) -> HTMLResponse:
        projects = ProjectService(database).list_projects()
        if len(projects) == 1:
            return _redirect(f"/m/{projects[0]['slug']}")
        return templates.TemplateResponse(request, "mobile_home.html", {"projects": projects})

    @app.get("/m/{project_slug}", response_class=HTMLResponse)
    def mobile_project(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.project_overview(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "mobile_project.html", payload)

    @app.get("/m/{project_slug}/cards/{card_key}", response_class=HTMLResponse)
    def mobile_card(request: Request, project_slug: str, card_key: str) -> HTMLResponse:
        try:
            payload = ui.card_detail(project_slug, card_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "mobile_card.html", payload)

    @app.get("/m/{project_slug}/review/next")
    def mobile_review_next(project_slug: str) -> RedirectResponse:
        try:
            payload = ui.review_queue(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        first_open = next((item for item in payload["reviews"] if item.get("status") == "open"), None)
        if first_open:
            return _redirect(f"/m/{project_slug}/review/{first_open['id']}")
        return _redirect(f"/m/{project_slug}")

    @app.get("/m/{project_slug}/review", response_class=HTMLResponse)
    def mobile_review_queue(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.review_queue(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "mobile_review.html", payload)

    @app.get("/m/{project_slug}/review/{review_id}", response_class=HTMLResponse)
    def mobile_review_item(request: Request, project_slug: str, review_id: int) -> HTMLResponse:
        try:
            payload = ui.mobile_review_item(project_slug, review_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "mobile_review_item.html", payload)

    @app.get("/m/{project_slug}/jobs", response_class=HTMLResponse)
    def mobile_jobs(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.job_queue(project_slug)
            payload["resume_plan"] = ResumeService(database).plan_project(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "mobile_jobs.html", payload)

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





    @app.get("/projects/{project_slug}/labs", response_class=HTMLResponse)
    def labs_page(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = ui.lab_dashboard(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "labs.html", payload)

    @app.post("/projects/{project_slug}/labs/prompt/create")
    def create_prompt_lab_case(
        project_slug: str,
        template_key: str = Form(...),
        target_type: str = Form("project"),
        target_id: str = Form(""),
        notes: str = Form(""),
    ) -> RedirectResponse:
        PromptLabService(database).create_case(PromptLabCaseSpec(project_slug=project_slug, template_key=template_key, target_type=target_type, target_id=target_id, notes=notes))
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/prompt/{case_key}/run")
    def run_prompt_lab_case(project_slug: str, case_key: str, variant_notes: str = Form("")) -> RedirectResponse:
        PromptLabService(database).run_case(project_slug, case_key, variant_notes=variant_notes, use_mock=True)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/prompt/{case_key}/promote-note")
    def promote_prompt_lab_note(project_slug: str, case_key: str) -> RedirectResponse:
        PromptLabService(database).write_promotion_note(project_slug, case_key)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/prompt/{case_key}/promote-request")
    def request_prompt_lab_promotion(project_slug: str, case_key: str, run_key: str = Form(""), notes: str = Form("")) -> RedirectResponse:
        try:
            LabPromotionService(database).create_prompt_template_request(project_slug, case_key, run_key=run_key or None, notes=notes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/image/create")
    def create_image_lab_case(project_slug: str, card_key: str = Form(...), notes: str = Form("")) -> RedirectResponse:
        ImageLabService(database).create_case(project_slug, card_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/image/{case_key}/run")
    def run_image_lab_case(project_slug: str, case_key: str, prompt_append: str = Form(""), count: int = Form(4)) -> RedirectResponse:
        ImageLabService(database).run_attempt(project_slug, case_key, prompt_append=prompt_append, count=count)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/image/{case_key}/recommend")
    def recommend_image_lab_case(project_slug: str, case_key: str, notes: str = Form("")) -> RedirectResponse:
        ImageLabService(database).write_recommendation(project_slug, case_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/image/{case_key}/promote-request")
    def request_image_lab_promotion(project_slug: str, case_key: str, attempt_key: str = Form(""), notes: str = Form("")) -> RedirectResponse:
        try:
            ImageLabService(database).propose_art_prompt_update(project_slug, case_key, attempt_key=attempt_key or None, notes=notes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/promotions/{request_key}/approve")
    def approve_lab_promotion(project_slug: str, request_key: str, notes: str = Form("")) -> RedirectResponse:
        LabPromotionService(database).approve_request(project_slug, request_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/promotions/{request_key}/reject")
    def reject_lab_promotion(project_slug: str, request_key: str, notes: str = Form("")) -> RedirectResponse:
        LabPromotionService(database).reject_request(project_slug, request_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/labs")

    @app.post("/projects/{project_slug}/labs/promotions/{request_key}/apply")
    def apply_lab_promotion(project_slug: str, request_key: str) -> RedirectResponse:
        try:
            LabPromotionService(database).apply_request(project_slug, request_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/labs")

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

    @app.post("/projects/{project_slug}/integrations/lmstudio/save")
    def save_lmstudio_settings(
        project_slug: str,
        base_url: str = Form(...),
        model: str = Form(...),
        review_model: str = Form(...),
        timeout_seconds: float = Form(300.0),
        max_tokens: str = Form(""),
        api_key: str = Form(""),
        clear_api_key: str = Form(""),
    ) -> RedirectResponse:
        IntegrationConfigService(database.settings).save_lmstudio(
            base_url=base_url,
            model=model,
            review_model=review_model,
            timeout_seconds=timeout_seconds,
            max_tokens=_optional_int(max_tokens),
            api_key=api_key or None,
            clear_api_key=clear_api_key == "yes",
        )
        return _redirect(f"/projects/{project_slug}/integrations")

    @app.post("/projects/{project_slug}/integrations/comfy/save")
    def save_comfy_settings(
        project_slug: str,
        base_url: str = Form(...),
        input_dir: str = Form(...),
        output_dir: str = Form(...),
        timeout_seconds: float = Form(1800.0),
        poll_interval_seconds: float = Form(1.0),
        api_key: str = Form(""),
        clear_api_key: str = Form(""),
    ) -> RedirectResponse:
        IntegrationConfigService(database.settings).save_comfyui(
            base_url=base_url,
            input_dir=input_dir,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            api_key=api_key or None,
            clear_api_key=clear_api_key == "yes",
        )
        return _redirect(f"/projects/{project_slug}/integrations")

    @app.get("/projects/{project_slug}/integrations/lmstudio/health")
    def lmstudio_health(project_slug: str) -> JSONResponse:
        health = LMStudioClient().health_detail()
        return JSONResponse(
            {"ok": health.ok, "base_url": health.base_url, "models": health.models, "error": health.error},
            status_code=200 if health.ok else 503,
        )

    @app.get("/projects/{project_slug}/integrations/comfy/health")
    def comfy_health(project_slug: str) -> JSONResponse:
        health = ComfyClient().health_detail()
        return JSONResponse(
            {"ok": health.ok, "base_url": health.base_url, "raw": health.raw, "error": health.error},
            status_code=200 if health.ok else 503,
        )


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


    @app.get("/projects/{project_slug}/prompt-studio", response_class=HTMLResponse)
    def prompt_studio(request: Request, project_slug: str) -> HTMLResponse:
        try:
            payload = PromptTemplateStudioService(database).dashboard(project_slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "prompt_studio.html", payload)

    @app.post("/projects/{project_slug}/prompt-studio/sync")
    def prompt_studio_sync(project_slug: str) -> RedirectResponse:
        PromptTemplateVersionService(database).sync_project(project_slug)
        return _redirect(f"/projects/{project_slug}/prompt-studio")

    @app.post("/projects/{project_slug}/prompt-studio/{template_key}/propose")
    def prompt_studio_propose(project_slug: str, template_key: str, summary: str = Form("")) -> RedirectResponse:
        result = PromptTemplateStudioService(database).create_manual_proposal(project_slug, template_key=template_key, summary=summary)
        return _redirect(f"/projects/{project_slug}/prompt-studio/{result['version_key']}")

    @app.get("/projects/{project_slug}/prompt-studio/{version_key}", response_class=HTMLResponse)
    def prompt_studio_version(request: Request, project_slug: str, version_key: str) -> HTMLResponse:
        try:
            payload = PromptTemplateStudioService(database).version_detail(project_slug, version_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.TemplateResponse(request, "prompt_studio_version.html", payload)

    @app.post("/projects/{project_slug}/prompt-studio/{version_key}/update")
    def prompt_studio_update(project_slug: str, version_key: str, markdown: str = Form(...), summary: str = Form("")) -> RedirectResponse:
        try:
            PromptTemplateStudioService(database).update_version_markdown(project_slug, version_key, markdown=markdown, summary=summary)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/prompt-studio/{version_key}")

    @app.post("/projects/{project_slug}/prompt-studio/{version_key}/approve")
    def prompt_studio_approve(project_slug: str, version_key: str, notes: str = Form("")) -> RedirectResponse:
        PromptTemplateVersionService(database).approve_version(project_slug, version_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/prompt-studio/{version_key}")

    @app.post("/projects/{project_slug}/prompt-studio/{version_key}/reject")
    def prompt_studio_reject(project_slug: str, version_key: str, notes: str = Form("")) -> RedirectResponse:
        PromptTemplateVersionService(database).reject_version(project_slug, version_key, notes=notes)
        return _redirect(f"/projects/{project_slug}/prompt-studio/{version_key}")

    @app.post("/projects/{project_slug}/prompt-studio/{version_key}/activate")
    def prompt_studio_activate(project_slug: str, version_key: str) -> RedirectResponse:
        try:
            PromptTemplateVersionService(database).activate_version(project_slug, version_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect(f"/projects/{project_slug}/prompt-studio/{version_key}")

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
        export_type = request.query_params.get("export")
        export_path = request.query_params.get("path")
        if export_type and export_path:
            payload["export_result"] = {
                "type": export_type,
                "path": export_path,
            }
        return templates.TemplateResponse(request, "set_detail.html", payload)

    @app.post("/projects/{project_slug}/sets/{set_code}/batches/generate")
    def generate_batch(
        project_slug: str,
        set_code: str,
        request_text: str = Form("Generate a balanced gothic fantasy card batch."),
        count: int = Form(12),
        live: str = Form(""),
    ) -> RedirectResponse:
        result = CardBatchService(database).generate_batch(
            project_slug,
            set_code,
            count=count,
            request_text=request_text,
            use_mock=live != "yes",
        )
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
            result = service.export_json(project_slug, set_code)
        elif export_type == "csv":
            result = service.export_csv(project_slug, set_code)
        elif export_type == "markdown":
            result = service.export_markdown_catalog(project_slug, set_code)
        elif export_type == "png":
            result = service.export_png_bundle(project_slug, set_code)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported export type: {export_type}")
        return _redirect(
            f"/projects/{project_slug}/sets/{set_code}?export={quote(export_type)}&path={quote(result['output_path'])}#exports"
        )

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
    def autofill_card(project_slug: str, card_key: str, live: str = Form("")) -> RedirectResponse:
        CardAutofillService(database).autofill_card(project_slug, card_key, use_mock=live != "yes")
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/refine")
    def refine_card(project_slug: str, card_key: str, live: str = Form("")) -> RedirectResponse:
        CardRefinementService(database).refine_card(project_slug, card_key, use_mock=live != "yes")
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/auto-review")
    def auto_review_card(project_slug: str, card_key: str) -> RedirectResponse:
        AutoReviewService(database).review_card_text(project_slug, card_key)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")


    @app.post("/projects/{project_slug}/cards/{card_key}/art/prepare-comfy")
    def prepare_comfy_art(project_slug: str, card_key: str, workflow_key: str = Form("stub.card_art.t2i.v1")) -> RedirectResponse:
        ComfyArtService(database).prepare_card_art(project_slug, card_key, workflow_key=workflow_key, submit=False)
        return _redirect(f"/projects/{project_slug}/cards/{card_key}")

    @app.post("/projects/{project_slug}/cards/{card_key}/art/submit-comfy")
    def submit_comfy_art(
        project_slug: str,
        card_key: str,
        workflow_key: str = Form("stub.card_art.t2i.v1"),
        seed: str = Form(""),
        width: str = Form(""),
        height: str = Form(""),
    ) -> RedirectResponse:
        ComfyArtService(database).prepare_card_art(
            project_slug,
            card_key,
            workflow_key=workflow_key,
            seed=_optional_int(seed),
            width=_optional_int(width),
            height=_optional_int(height),
            submit=True,
        )
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
        tags: str = Form(""),
        return_to: str = Form(""),
    ) -> RedirectResponse:
        try:
            decision_enum = ReviewDecision(decision)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsupported decision: {decision}") from exc
        tag_list = [item.strip().lower().replace(" ", "_") for item in tags.replace(",", "\n").splitlines() if item.strip()]
        ReviewService(database).decide(review_id, decision=decision_enum, reason=reason, notes=notes, tags=tag_list)
        return _redirect(safe_redirect_target(return_to or f"/projects/{project_slug}/review"))

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
