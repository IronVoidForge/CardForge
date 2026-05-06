from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.templates.template_service import TemplateService, TemplateValidationError

app = typer.Typer(help="Card front/back template registry commands")


@app.command("sync")
def template_sync(project_slug: str) -> None:
    ensure_db()
    echo_json(TemplateService().sync_project_templates(project_slug))


@app.command("list")
def template_list(project_slug: str) -> None:
    ensure_db()
    for item in TemplateService().list_templates(project_slug):
        typer.echo(
            f"{item['template_key']}\t{item['template_type']}\t{item['card_type']}\t"
            f"{item['canvas_width']}x{item['canvas_height']}\t{item['status']}"
        )


@app.command("show")
def template_show(project_slug: str, template_key: str) -> None:
    ensure_db()
    echo_json(TemplateService().get_template(project_slug, template_key))


@app.command("validate")
def template_validate(project_slug: str, template_key: str) -> None:
    ensure_db()
    try:
        echo_json(TemplateService().validate_template(project_slug, template_key))
    except TemplateValidationError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("preview")
def template_preview(project_slug: str, template_key: str) -> None:
    ensure_db()
    echo_json(TemplateService().render_preview(project_slug, template_key))


@app.command("update-json")
def template_update_json(project_slug: str, template_key: str, path: Path) -> None:
    ensure_db()
    if not path.exists():
        raise typer.BadParameter(f"Template JSON file not found: {path}")
    echo_json(TemplateService().update_template(project_slug, template_key, path.read_text(encoding="utf-8")))
