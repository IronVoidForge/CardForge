from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.export.export_service import ExportService

app = typer.Typer(help="Export commands")


@app.command("json")
def export_json(project_slug: str, set_code: str) -> None:
    ensure_db()
    echo_json(ExportService().export_json(project_slug, set_code))


@app.command("csv")
def export_csv(project_slug: str, set_code: str) -> None:
    ensure_db()
    echo_json(ExportService().export_csv(project_slug, set_code))


@app.command("markdown")
def export_markdown(project_slug: str, set_code: str) -> None:
    ensure_db()
    echo_json(ExportService().export_markdown_catalog(project_slug, set_code))


@app.command("png")
def export_png(project_slug: str, set_code: str) -> None:
    ensure_db()
    echo_json(ExportService().export_png_bundle(project_slug, set_code))
