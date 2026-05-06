from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.generation.card_repair_service import CardRepairService
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.review.auto_review_service import AutoReviewService

app = typer.Typer(help="Card commands")


@app.command("create")
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
    ensure_db()
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


@app.command("list")
def card_list(project_slug: str, set_code: str | None = None) -> None:
    ensure_db()
    for card in CardService().list_cards(project_slug, set_code):
        typer.echo(f"{card['card_key']}\t{card['name']}\t{card['card_type']}\t{card['status']}")


@app.command("show")
def card_show(project_slug: str, card_key: str) -> None:
    ensure_db()
    card = CardService().get_card(project_slug, card_key)
    echo_json({key: card[key] for key in card.keys()})


@app.command("validate")
def card_validate(project_slug: str, card_key: str) -> None:
    ensure_db()
    echo_json(CardService().validate_card(project_slug, card_key))


@app.command("autofill")
def card_autofill(
    project_slug: str,
    card_key: str,
    force: bool = typer.Option(False, "--force"),
    live: bool = typer.Option(False, "--live"),
) -> None:
    ensure_db()
    echo_json(CardAutofillService().autofill_card(project_slug, card_key, use_mock=not live, force=force))


@app.command("refine")
def card_refine(
    project_slug: str,
    card_key: str,
    live: bool = typer.Option(False, "--live"),
    no_autofill: bool = typer.Option(False, "--no-autofill"),
) -> None:
    ensure_db()
    echo_json(CardRefinementService().refine_card(project_slug, card_key, use_mock=not live, autofill_first=not no_autofill))


@app.command("auto-review")
def card_auto_review(project_slug: str, card_key: str) -> None:
    ensure_db()
    echo_json(AutoReviewService().review_card_text(project_slug, card_key))


@app.command("versions")
def card_versions(project_slug: str, card_key: str) -> None:
    ensure_db()
    for row in CardService().list_versions(project_slug, card_key):
        typer.echo(f"v{row['version_number']:03d}\t{row['source']}\t{row['change_reason']}")


@app.command("repair-rules")
def card_repair_rules(project_slug: str, card_key: str, reason: str = "offline rules text repair") -> None:
    ensure_db()
    echo_json(CardRepairService().repair_rules_text_offline(project_slug, card_key, reason=reason))
