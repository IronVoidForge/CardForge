from __future__ import annotations

import typer

from cardforge.integrations.comfyui import ComfyClient
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService

llm_app = typer.Typer(help="LM Studio commands")
comfy_app = typer.Typer(help="ComfyUI commands")


@llm_app.command("health")
def llm_health() -> None:
    typer.echo("ok" if LMStudioClient().health() else "unavailable")


@llm_app.command("test-prompt")
def llm_test_prompt(prompt: str) -> None:
    result = LMStudioClient().chat(system_prompt="You are a concise card design assistant.", user_prompt=prompt)
    if not result.ok:
        typer.echo(f"ERROR: {result.error}")
        raise typer.Exit(1)
    typer.echo(result.text)


@comfy_app.command("health")
def comfy_health() -> None:
    typer.echo("ok" if ComfyClient().health() else "unavailable")


@comfy_app.command("sync-workflows")
def comfy_sync_workflows() -> None:
    from cardforge.cli.bootstrap import echo_json, ensure_db

    ensure_db()
    echo_json(WorkflowRegistryService().sync_defaults())


@comfy_app.command("workflows")
def comfy_workflows() -> None:
    from cardforge.cli.bootstrap import echo_json, ensure_db

    ensure_db()
    echo_json({"workflows": WorkflowRegistryService().list_workflows()})


@comfy_app.command("validate-workflow")
def comfy_validate_workflow(workflow_key: str = "stub.card_art.t2i.v1") -> None:
    from cardforge.cli.bootstrap import echo_json, ensure_db

    ensure_db()
    echo_json(WorkflowRegistryService().validate_workflow(workflow_key))


@comfy_app.command("prepare-card-art")
def comfy_prepare_card_art(
    project_slug: str,
    card_key: str,
    workflow_key: str = "stub.card_art.t2i.v1",
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    from cardforge.cli.bootstrap import echo_json, ensure_db

    ensure_db()
    echo_json(ComfyArtService().prepare_card_art(project_slug, card_key, workflow_key=workflow_key, seed=seed, width=width, height=height, submit=False))
