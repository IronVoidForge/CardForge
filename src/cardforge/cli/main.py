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
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService
from cardforge.services.status.status_service import StatusService

app = typer.Typer(help="CardForge local card pipeline")
db_app = typer.Typer(help="Database commands")
project_app = typer.Typer(help="Project commands")
set_app = typer.Typer(help="Set commands")
card_app = typer.Typer(help="Card commands")
render_app = typer.Typer(help="Render commands")
review_app = typer.Typer(help="Review commands")
llm_app = typer.Typer(help="LM Studio commands")
comfy_app = typer.Typer(help="ComfyUI commands")
export_app = typer.Typer(help="Export commands")

app.add_typer(db_app, name="db")
app.add_typer(project_app, name="project")
app.add_typer(set_app, name="set")
app.add_typer(card_app, name="card")
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
    report = CardService().validate_card(project_slug, card_key)
    typer.echo(json.dumps(report, indent=2))


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


def _ensure_db() -> None:
    db = Database()
    with db.connection() as conn:
        migrate(conn)
