from __future__ import annotations

import typer

from cardforge.integrations.comfyui import ComfyClient
from cardforge.integrations.lmstudio import LMStudioClient

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
