from __future__ import annotations

from typing import Annotated

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.labs.lab_promotion_service import LabPromotionService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService

app = typer.Typer(help="Prompt template/package commands")
version_app = typer.Typer(help="Prompt template version commands")
app.add_typer(version_app, name="version")


@app.command("sync")
def prompt_sync(project_slug: str) -> None:
    ensure_db()
    PromptTemplateService().sync_templates(project_slug)
    echo_json(PromptTemplateVersionService().sync_project(project_slug))


@app.command("list")
def prompt_list(project_slug: str) -> None:
    ensure_db()
    PromptTemplateVersionService().sync_project(project_slug)
    for row in PromptTemplateService().list_templates(project_slug):
        typer.echo(f"{row['template_key']}\t{row['task']}\t{row['title']}\t{row.get('status', '')}")


@app.command("show")
def prompt_show(project_slug: str, template_key: str) -> None:
    ensure_db()
    template = PromptTemplateService().load_template(project_slug, template_key)
    echo_json(
        {
            "template_key": template.template_key,
            "title": template.title,
            "task": template.task,
            "path": str(template.path),
            "inputs": PromptTemplateService().parse_inputs_from_template(project_slug, template_key),
        }
    )


@version_app.command("list")
def version_list(project_slug: str, template_key: Annotated[str, typer.Option()] = "") -> None:
    ensure_db()
    PromptTemplateVersionService().sync_project(project_slug)
    echo_json(PromptTemplateVersionService().list_versions(project_slug, template_key or None))


@version_app.command("approve")
def version_approve(project_slug: str, version_key: str, notes: str = "") -> None:
    ensure_db()
    echo_json(PromptTemplateVersionService().approve_version(project_slug, version_key, notes=notes))


@version_app.command("reject")
def version_reject(project_slug: str, version_key: str, notes: str = "") -> None:
    ensure_db()
    echo_json(PromptTemplateVersionService().reject_version(project_slug, version_key, notes=notes))


@version_app.command("activate")
def version_activate(project_slug: str, version_key: str) -> None:
    ensure_db()
    echo_json(PromptTemplateVersionService().activate_version(project_slug, version_key))


@version_app.command("propose-from-lab")
def version_propose_from_lab(project_slug: str, case_key: str, run_key: str = "", notes: str = "") -> None:
    ensure_db()
    echo_json(LabPromotionService().create_prompt_template_request(project_slug, case_key, run_key=run_key or None, notes=notes))
