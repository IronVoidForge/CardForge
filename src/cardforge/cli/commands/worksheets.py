from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.worksheets.worksheet_service import WorksheetService

app = typer.Typer(help="Worksheet import/render/export commands")


@app.command("import")
def worksheet_import(
    project_slug: str,
    worksheet_json: Path,
    replace_existing: bool = typer.Option(False, "--replace-existing"),
) -> None:
    ensure_db()
    echo_json(WorksheetService().import_worksheets(project_slug, worksheet_json, replace_existing=replace_existing))


@app.command("render")
def worksheet_render(project_slug: str, low_ink: bool = typer.Option(True, "--low-ink/--full-ink")) -> None:
    ensure_db()
    echo_json(WorksheetService().render_worksheets(project_slug, low_ink=low_ink))


@app.command("export")
def worksheet_export(project_slug: str) -> None:
    ensure_db()
    echo_json(WorksheetService().export_worksheets(project_slug))
