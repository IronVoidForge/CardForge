from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.importers.mmm_import_service import MMMImportService

app = typer.Typer(help="Import external game data into CardForge")


@app.command("mmm")
def import_mmm(
    project_slug: str,
    project_name: str = typer.Option("Magic, Math, & Monsters", "--project-name"),
    project_description: str = typer.Option("Imported Magic, Math, & Monsters production project.", "--project-description"),
    player_deck: Path | None = typer.Option(None, "--player-deck", help="MMM Player Deck JSON file."),
    loot: Path | None = typer.Option(None, "--loot", help="MMM Loot Insert JSON file."),
    monsters: Path | None = typer.Option(None, "--monsters", help="MMM Monster Deck JSON file."),
    worksheets: Path | None = typer.Option(None, "--worksheets", help="MMM Worksheet Pad JSON file."),
    player_set_code: str = typer.Option("PLAYER", "--player-set-code"),
    monster_set_code: str = typer.Option("MONSTER", "--monster-set-code"),
    create_project: bool = typer.Option(True, "--create-project/--no-create-project"),
    create_sets: bool = typer.Option(True, "--create-sets/--no-create-sets"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Delete existing cards in touched sets before import."),
) -> None:
    ensure_db()
    result = MMMImportService().import_mmm(
        project_slug,
        project_name=project_name,
        project_description=project_description,
        player_deck_path=player_deck,
        loot_path=loot,
        monsters_path=monsters,
        worksheets_path=worksheets,
        player_set_code=player_set_code,
        monster_set_code=monster_set_code,
        create_project=create_project,
        create_sets=create_sets,
        replace_existing=replace_existing,
    )
    echo_json(result)


@app.command("mmm-registries")
def import_mmm_registries(project_slug: str) -> None:
    """Install/refresh MMM card types, keywords, and templates in a project."""
    ensure_db()
    echo_json(MMMImportService().ensure_mmm_registries(project_slug))
