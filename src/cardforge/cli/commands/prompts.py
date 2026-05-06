from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.prompts.prompt_package import PromptTemplateService

app = typer.Typer(help="Prompt template/package commands")


@app.command("list")
def prompt_list(project_slug: str) -> None:
    ensure_db()
    for row in PromptTemplateService().list_templates(project_slug):
        typer.echo(f"{row['template_key']}\t{row['task']}\t{row['title']}")


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
