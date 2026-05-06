from __future__ import annotations

import json
from pathlib import Path

import typer

from cardforge.config import load_settings
from cardforge.db.schema import migrate, reset
from cardforge.db.session import Database
from cardforge.domain.enums import ReviewDecision
from cardforge.integrations.comfyui import ComfyClient
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.art.art_prompt_service import ArtPromptService
from cardforge.services.balance.balance_review_service import BalanceReviewService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_repair_service import CardRepairService
from cardforge.services.generation.rules_review_service import RulesReviewService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.review_service import ReviewService
from cardforge.services.rework.card_rework_service import CardReworkService
from cardforge.services.rework.rework_service import ReworkService
from cardforge.services.sets.set_service import SetService
from cardforge.services.status.status_service import StatusService

app = typer.Typer(help="CardForge local card pipeline")
db_app = typer.Typer(help="Database commands")
project_app = typer.Typer(help="Project commands")
set_app = typer.Typer(help="Set commands")
card_app = typer.Typer(help="Card commands")
batch_app = typer.Typer(help="Batch generation commands")
art_app = typer.Typer(help="Art prompt/candidate commands")
rework_app = typer.Typer(help="Rework request commands")
render_app = typer.Typer(help="Render commands")
review_app = typer.Typer(help="Review commands")
llm_app = typer.Typer(help="LM Studio commands")
comfy_app = typer.Typer(help="ComfyUI commands")
export_app = typer.Typer(help="Export commands")

app.add_typer(db_app, name="db")
app.add_typer(project_app, name="project")
app.add_typer(set_app, name="set")
app.add_typer(card_app, name="card")
app.add_typer(batch_app, name="batch")
app.add_typer(art_app, name="art")
app.add_typer(rework_app, name="rework")
app.add_typer(render_app, name="render")
app.add_typer(review_app, name="review")
app.add_typer(llm_app, name="llm")
app.add_typer(comfy_app, name="comfy")
app.add_typer(export_app, name="export")


@db_app.command("init")
def db_init() -> None:
    db = Database()
    with db.connection() as conn:
        migrate(conn)
    typer.echo(f"Database initialized: {db.path}")


@db_app.command("reset")
def db_reset(yes: bool = typer.Option(False, "--yes", help="Confirm destructive reset.")) -> None:
    if not yes:
        raise typer.BadParameter("Pass --yes to reset the database.")
    db = Database()
    with db.connection() as conn:
        reset(conn)
    typer.echo(f"Database reset: {db.path}")


@project_app.command("create")
def project_create(slug: str, name: str = "", description: str = "") -> None:
    _ensure_db()
    project = ProjectService().create_project(slug, name=name, description=description)
    typer.echo(f"Created project {project['slug']} at {project['root_path']}")


@project_app.command("list")
def project_list() -> None:
    _ensure_db()
    for project in ProjectService().list_projects():
        typer.echo(f"{project['slug']}\t{project['name']}\t{project['status']}")


@project_app.command("status")
def project_status(slug: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(StatusService().project_status(slug), indent=2))


@set_app.command("create")
def set_create(project_slug: str, name: str = typer.Option(..., "--name"), description: str = "", target_card_count: int = 0) -> None:
    _ensure_db()
    set_row = SetService().create_set(project_slug, name=name, description=description, target_card_count=target_card_count)
    typer.echo(f"Created set {set_row['set_code']}: {set_row['name']}")


@set_app.command("list")
def set_list(project_slug: str) -> None:
    _ensure_db()
    for row in SetService().list_sets(project_slug):
        typer.echo(f"{row['set_code']}\t{row['name']}\t{row['status']}")


@card_app.command("create")
def card_create(
    project_slug: str,
    set_code: str,
    name: str = typer.Option(..., "--name"),
    card_type: str = typer.Option("creature", "--type"),
    rules_text: str = "",
    rarity: str = "common",
    faction: str = "",
    attack: int | None = None,
    health: int | None = None,
    cost: int = 0,
    flavor_text: str = "",
    art_direction: str = "",
) -> None:
    _ensure_db()
    card = CardService().create_card(
        project_slug,
        set_code,
        name=name,
        card_type=card_type,
        rules_text=rules_text,
        rarity=rarity,
        faction=faction,
        attack=attack,
        health=health,
        cost=cost,
        flavor_text=flavor_text,
        art_direction=art_direction,
    )
    typer.echo(f"Created card {card['card_key']}: {card['name']}")


@card_app.command("list")
def card_list(project_slug: str, set_code: str | None = None) -> None:
    _ensure_db()
    for card in CardService().list_cards(project_slug, set_code):
        typer.echo(f"{card['card_key']}\t{card['name']}\t{card['card_type']}\t{card['status']}")


@card_app.command("show")
def card_show(project_slug: str, card_key: str) -> None:
    _ensure_db()
    card = CardService().get_card(project_slug, card_key)
    typer.echo(json.dumps({key: card[key] for key in card.keys()}, indent=2))


@card_app.command("validate")
def card_validate(project_slug: str, card_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(CardService().validate_card(project_slug, card_key), indent=2))


@card_app.command("versions")
def card_versions(project_slug: str, card_key: str) -> None:
    _ensure_db()
    for row in CardService().list_versions(project_slug, card_key):
        typer.echo(f"v{row['version_number']:03d}\t{row['source']}\t{row['change_reason']}")


@card_app.command("repair-rules")
def card_repair_rules(project_slug: str, card_key: str, reason: str = "offline rules text repair") -> None:
    _ensure_db()
    typer.echo(json.dumps(CardRepairService().repair_rules_text_offline(project_slug, card_key, reason=reason), indent=2))


@batch_app.command("generate")
def batch_generate(
    project_slug: str,
    set_code: str,
    count: int = typer.Option(12, "--count", help="Number of cards to generate."),
    request: str = typer.Option("", "--request", help="Freeform batch request."),
    request_file: Path | None = typer.Option(None, "--request-file", help="Read request from markdown/text file."),
    live: bool = typer.Option(False, "--live", help="Call LM Studio instead of deterministic offline simulation."),
) -> None:
    _ensure_db()
    request_text = _read_text_arg(request, request_file) or "Generate a balanced gothic fantasy card batch."
    result = CardBatchService().generate_batch(project_slug, set_code, count=count, request_text=request_text, use_mock=not live)
    typer.echo(json.dumps(result, indent=2))


@batch_app.command("list")
def batch_list(project_slug: str, set_code: str | None = None) -> None:
    _ensure_db()
    for row in CardBatchService().list_batches(project_slug, set_code):
        typer.echo(f"{row['batch_key']}\t{row['target_count']}\t{row['status']}")


@batch_app.command("show")
def batch_show(project_slug: str, batch_key: str) -> None:
    _ensure_db()
    row = CardBatchService().get_batch(project_slug, batch_key)
    typer.echo(json.dumps({key: row[key] for key in row.keys()}, indent=2))


@batch_app.command("validate")
def batch_validate(project_slug: str, batch_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(CardBatchService().validate_batch(project_slug, batch_key), indent=2))


@batch_app.command("balance-review")
def batch_balance_review(project_slug: str, batch_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(BalanceReviewService().review_batch(project_slug, batch_key), indent=2))


@batch_app.command("rules-review")
def batch_rules_review(project_slug: str, batch_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(RulesReviewService().review_batch(project_slug, batch_key), indent=2))


@art_app.command("prompt")
def art_prompt(project_slug: str, card_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(ArtPromptService().create_prompt(project_slug, card_key), indent=2))


@art_app.command("generate-dummy")
def art_generate_dummy(project_slug: str, card_key: str, count: int = typer.Option(4, "--count"), seed: int | None = None) -> None:
    _ensure_db()
    typer.echo(json.dumps(ArtCandidateService().generate_dummy_candidates(project_slug, card_key, count=count, seed=seed), indent=2))


@art_app.command("list")
def art_list(project_slug: str, card_key: str) -> None:
    _ensure_db()
    for row in ArtCandidateService().list_candidates(project_slug, card_key):
        typer.echo(f"{row['candidate_key']}\t{row['status']}\t{row['image_path']}")


@art_app.command("approve")
def art_approve(project_slug: str, candidate_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(ArtCandidateService().approve(project_slug, candidate_key), indent=2))


@art_app.command("reject")
def art_reject(project_slug: str, candidate_key: str, reason: str = "") -> None:
    _ensure_db()
    typer.echo(json.dumps(ArtCandidateService().reject(project_slug, candidate_key, reason=reason), indent=2))


@art_app.command("lock")
def art_lock(project_slug: str, candidate_key: str) -> None:
    _ensure_db()
    typer.echo(json.dumps(ArtCandidateService().lock(project_slug, candidate_key), indent=2))


@rework_app.command("create")
def rework_create(project_slug: str, target_type: str, target_id: str, rework_type: str, reason: str = "", notes: str = "", tags: str = "") -> None:
    _ensure_db()
    result = ReworkService().create_request(
        project_slug,
        target_type=target_type,
        target_id=target_id,
        rework_type=rework_type,
        reason=reason,
        operator_notes=notes,
        failure_tags=[item.strip() for item in tags.split(",") if item.strip()],
    )
    typer.echo(json.dumps(result, indent=2))


@rework_app.command("list")
def rework_list(project_slug: str) -> None:
    _ensure_db()
    for row in ReworkService().list_requests(project_slug):
        typer.echo(f"{row['id']}\t{row['target_type']}:{row['target_id']}\t{row['rework_type']}\t{row['status']}")


@rework_app.command("repair-rules")
def rework_repair_rules(project_slug: str, card_key: str, reason: str = "shorten for template") -> None:
    _ensure_db()
    typer.echo(json.dumps(CardReworkService().repair_rules_text(project_slug, card_key, reason=reason), indent=2))


@render_app.command("card")
def render_card(project_slug: str, card_key: str, placeholder_art: bool = True) -> None:
    _ensure_db()
    result = CardRenderer().render_card(project_slug, card_key, placeholder_art=placeholder_art)
    typer.echo(json.dumps(result, indent=2))


@review_app.command("list")
def review_list(project_slug: str) -> None:
    _ensure_db()
    project = ProjectService().get_project(project_slug)
    rows = ReviewService().list_open(project["id"])
    if not rows:
        typer.echo("No open review items.")
        return
    for row in rows:
        typer.echo(f"{row['id']}\t{row['review_type']}\t{row['target_type']}:{row['target_id']}\t{row['title']}")


@review_app.command("decide")
def review_decide(review_item_id: int, decision: ReviewDecision, reason: str = "", tags: str = "") -> None:
    _ensure_db()
    row = ReviewService().decide(
        review_item_id,
        decision=decision,
        reason=reason,
        tags=[item.strip() for item in tags.split(",") if item.strip()],
    )
    typer.echo(f"Review {row['id']} now {row['status']}")


@llm_app.command("health")
def llm_health() -> None:
    typer.echo("ok" if LMStudioClient().health() else "unavailable")


@llm_app.command("test-prompt")
def llm_test_prompt(prompt: str) -> None:
    result = LMStudioClient().chat(system_prompt="You are a concise card design assistant.", user_prompt=prompt)
    if not result.ok:
        typer.echo(f"ERROR: {result.error}")
        raise typer.Exit(1)
    typer.echo(result.text)


@comfy_app.command("health")
def comfy_health() -> None:
    typer.echo("ok" if ComfyClient().health() else "unavailable")


@export_app.command("json")
def export_json(project_slug: str, set_code: str) -> None:
    _ensure_db()
    cards = CardService().list_cards(project_slug, set_code)
    settings = load_settings()
    project_root = settings.workspace_root / "projects" / project_slug
    out = project_root / "exports" / "json" / f"{set_code.lower()}_cards.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [{key: card[key] for key in card.keys()} for card in cards]
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"Wrote {out}")


def _read_text_arg(inline: str, file_path: Path | None) -> str:
    if file_path is not None:
        return file_path.read_text(encoding="utf-8")
    return inline.strip()


def _ensure_db() -> None:
    db = Database()
    with db.connection() as conn:
        migrate(conn)
