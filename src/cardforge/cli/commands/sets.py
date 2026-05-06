from __future__ import annotations

import typer

from cardforge.cli.bootstrap import ensure_db
from cardforge.services.sets.set_service import SetService

app = typer.Typer(help="Set commands")


@app.command("create")
def set_create(
    project_slug: str,
    name: str = typer.Option(..., "--name"),
    description: str = "",
    target_card_count: int = 0,
) -> None:
    ensure_db()
    set_row = SetService().create_set(project_slug, name=name, description=description, target_card_count=target_card_count)
    typer.echo(f"Created set {set_row['set_code']}: {set_row['name']}")


@app.command("list")
def set_list(project_slug: str) -> None:
    ensure_db()
    for row in SetService().list_sets(project_slug):
        typer.echo(f"{row['set_code']}\t{row['name']}\t{row['status']}")
