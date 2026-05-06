from __future__ import annotations

import json
from typing import Annotated

import typer

from cardforge.services.labs.image_lab_service import ImageLabService
from cardforge.services.labs.lab_promotion_service import LabPromotionService
from cardforge.services.labs.prompt_lab_service import PromptLabCaseSpec, PromptLabService

app = typer.Typer(help="Prompt Lab and Image Lab workbenches")
prompt_app = typer.Typer(help="Prompt template experiments")
image_app = typer.Typer(help="Card art prompt experiments")
promotion_app = typer.Typer(help="Lab promotion gates")
app.add_typer(prompt_app, name="prompt")
app.add_typer(image_app, name="image")
app.add_typer(promotion_app, name="promotion")


@prompt_app.command("create")
def prompt_create(
    project_slug: str,
    template_key: str,
    target_type: Annotated[str, typer.Option(help="project, set, card, or batch")] = "project",
    target_id: Annotated[str, typer.Option(help="Target key such as SET001 or CARD_0001")] = "",
    notes: Annotated[str, typer.Option(help="Experiment goal or prompt hypothesis")] = "",
) -> None:
    result = PromptLabService().create_case(PromptLabCaseSpec(project_slug=project_slug, template_key=template_key, target_type=target_type, target_id=target_id, notes=notes))
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prompt_app.command("list")
def prompt_list(project_slug: str) -> None:
    typer.echo(json.dumps(PromptLabService().list_cases(project_slug), indent=2, ensure_ascii=False))


@prompt_app.command("run")
def prompt_run(project_slug: str, case_key: str, variant_notes: Annotated[str, typer.Option()] = "") -> None:
    result = PromptLabService().run_case(project_slug, case_key, variant_notes=variant_notes, use_mock=True)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prompt_app.command("compare")
def prompt_compare(project_slug: str, case_key: str) -> None:
    typer.echo(json.dumps(PromptLabService().compare_runs(project_slug, case_key), indent=2, ensure_ascii=False))


@prompt_app.command("mark")
def prompt_mark(project_slug: str, case_key: str, run_key: str, status: str, notes: Annotated[str, typer.Option()] = "") -> None:
    result = PromptLabService().mark_run(project_slug, case_key, run_key, status=status, notes=notes)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prompt_app.command("promote-note")
def prompt_promote_note(project_slug: str, case_key: str, run_key: Annotated[str, typer.Option()] = "") -> None:
    result = PromptLabService().write_promotion_note(project_slug, case_key, run_key=run_key or None)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prompt_app.command("promote-request")
def prompt_promote_request(project_slug: str, case_key: str, run_key: Annotated[str, typer.Option()] = "", notes: Annotated[str, typer.Option()] = "") -> None:
    result = LabPromotionService().create_prompt_template_request(project_slug, case_key, run_key=run_key or None, notes=notes)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@prompt_app.command("promotions")
def prompt_promotions(project_slug: str, status: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().list_requests(project_slug, status=status or None), indent=2, ensure_ascii=False))


@prompt_app.command("approve-promotion")
def prompt_approve_promotion(project_slug: str, request_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().approve_request(project_slug, request_key, notes=notes), indent=2, ensure_ascii=False))


@prompt_app.command("reject-promotion")
def prompt_reject_promotion(project_slug: str, request_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().reject_request(project_slug, request_key, notes=notes), indent=2, ensure_ascii=False))


@prompt_app.command("apply-promotion")
def prompt_apply_promotion(project_slug: str, request_key: str) -> None:
    typer.echo(json.dumps(LabPromotionService().apply_request(project_slug, request_key), indent=2, ensure_ascii=False))


@image_app.command("create")
def image_create(project_slug: str, card_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    result = ImageLabService().create_case(project_slug, card_key, notes=notes)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@image_app.command("list")
def image_list(project_slug: str) -> None:
    typer.echo(json.dumps(ImageLabService().list_cases(project_slug), indent=2, ensure_ascii=False))


@image_app.command("run")
def image_run(
    project_slug: str,
    case_key: str,
    prompt_append: Annotated[str, typer.Option(help="Prompt wording to test in this attempt")] = "",
    count: Annotated[int, typer.Option(min=1, max=12)] = 4,
    seed: Annotated[int | None, typer.Option()] = None,
) -> None:
    result = ImageLabService().run_attempt(project_slug, case_key, prompt_append=prompt_append, count=count, seed=seed)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@image_app.command("review")
def image_review(
    project_slug: str,
    case_key: str,
    attempt_key: str,
    candidate_id: str,
    decision: Annotated[str, typer.Option()] = "maybe",
    rating: Annotated[int | None, typer.Option(min=1, max=5)] = None,
    notes: Annotated[str, typer.Option()] = "",
    success_tag: Annotated[list[str] | None, typer.Option()] = None,
    failure_tag: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    result = ImageLabService().review_candidate(
        project_slug,
        case_key,
        attempt_key,
        candidate_id,
        decision=decision,
        rating=rating,
        notes=notes,
        success_tags=success_tag or [],
        failure_tags=failure_tag or [],
    )
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@image_app.command("promote-request")
def image_promote_request(project_slug: str, case_key: str, attempt_key: Annotated[str, typer.Option()] = "", notes: Annotated[str, typer.Option()] = "") -> None:
    result = ImageLabService().propose_art_prompt_update(project_slug, case_key, attempt_key=attempt_key or None, notes=notes)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@image_app.command("propose-prompt-update")
def image_propose_prompt_update(project_slug: str, case_key: str, attempt_key: Annotated[str, typer.Option()] = "", notes: Annotated[str, typer.Option()] = "") -> None:
    result = ImageLabService().propose_art_prompt_update(project_slug, case_key, attempt_key=attempt_key or None, notes=notes)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@image_app.command("compare")
def image_compare(project_slug: str, case_key: str) -> None:
    typer.echo(json.dumps(ImageLabService().compare_attempts(project_slug, case_key), indent=2, ensure_ascii=False))


@image_app.command("recommend")
def image_recommend(project_slug: str, case_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(ImageLabService().write_recommendation(project_slug, case_key, notes=notes), indent=2, ensure_ascii=False))


@promotion_app.command("list")
def promotion_list(project_slug: str, status: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().list_requests(project_slug, status=status or None), indent=2, ensure_ascii=False))


@promotion_app.command("approve")
def promotion_approve(project_slug: str, request_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().approve_request(project_slug, request_key, notes=notes), indent=2, ensure_ascii=False))


@promotion_app.command("reject")
def promotion_reject(project_slug: str, request_key: str, notes: Annotated[str, typer.Option()] = "") -> None:
    typer.echo(json.dumps(LabPromotionService().reject_request(project_slug, request_key, notes=notes), indent=2, ensure_ascii=False))


@promotion_app.command("apply")
def promotion_apply(project_slug: str, request_key: str) -> None:
    typer.echo(json.dumps(LabPromotionService().apply_request(project_slug, request_key), indent=2, ensure_ascii=False))
