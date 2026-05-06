from __future__ import annotations

import json

import typer

from cardforge.cli.bootstrap import ensure_db
from cardforge.config import load_settings
from cardforge.services.cards.card_service import CardService

app = typer.Typer(help="Export commands")


@app.command("json")
def export_json(project_slug: str, set_code: str) -> None:
    ensure_db()
    cards = CardService().list_cards(project_slug, set_code)
    settings = load_settings()
    project_root = settings.workspace_root / "projects" / project_slug
    out = project_root / "exports" / "json" / f"{set_code.lower()}_cards.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [{key: card[key] for key in card.keys()} for card in cards]
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"Wrote {out}")
