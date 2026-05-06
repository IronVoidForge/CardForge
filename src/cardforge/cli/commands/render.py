from __future__ import annotations

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.render.card_renderer import CardRenderer

import typer

app = typer.Typer(help="Render commands")


@app.command("card")
def render_card(project_slug: str, card_key: str, placeholder_art: bool = True) -> None:
    ensure_db()
    echo_json(CardRenderer().render_card(project_slug, card_key, placeholder_art=placeholder_art))
