from __future__ import annotations

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.status.status_service import StatusService

import typer

app = typer.Typer(help="Project commands")


@app.command("create")
def project_create(slug: str, name: str = "", description: str = "") -> None:
    ensure_db()
    project = ProjectService().create_project(slug, name=name, description=description)
    typer.echo(f"Created project {project['slug']} at {project['root_path']}")


@app.command("list")
def project_list() -> None:
    ensure_db()
    for project in ProjectService().list_projects():
        typer.echo(f"{project['slug']}\t{project['name']}\t{project['status']}")


@app.command("status")
def project_status(slug: str) -> None:
    ensure_db()
    echo_json(StatusService().project_status(slug))
