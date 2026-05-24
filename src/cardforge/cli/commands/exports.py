from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.export.export_service import ExportService
from cardforge.services.export.print_sheet_service import PrintSheetExportService

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


@app.command("print-sheets")
def export_print_sheets(project_slug: str, set_code: str, side: str = typer.Option("front", "--side")) -> None:
    ensure_db()
    echo_json(PrintSheetExportService().export_print_sheets(project_slug, set_code, side=side))


@app.command("game-package")
def export_game_package(project_slug: str) -> None:
    ensure_db()
    echo_json(PrintSheetExportService().export_game_package(project_slug))
