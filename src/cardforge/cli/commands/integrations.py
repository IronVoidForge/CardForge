from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.integrations.comfyui import ComfyClient
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService
from cardforge.services.integrations.integration_config_service import IntegrationConfigService

llm_app = typer.Typer(help="LM Studio commands")
comfy_app = typer.Typer(help="ComfyUI commands")


@llm_app.command("configure")
def llm_configure(
    base_url: str = typer.Option("http://127.0.0.1:1234/v1", "--base-url", help="LM Studio OpenAI-compatible /v1 URL."),
    model: str = typer.Option("local-cardforge-model", "--model", help="Generation model id."),
    review_model: str = typer.Option("local-cardforge-review-model", "--review-model", help="Review model id."),
    timeout_seconds: float = typer.Option(300.0, "--timeout-seconds", min=1.0),
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Optional max tokens."),
    api_key: str = typer.Option("", "--api-key", help="Optional bearer token/API key."),
    clear_api_key: bool = typer.Option(False, "--clear-api-key", help="Remove saved LM Studio API key."),
) -> None:
    """Persist LM Studio network settings in workspace/config/integrations.json."""
    ensure_db()
    service = IntegrationConfigService()
    service.save_lmstudio(
        base_url=base_url,
        model=model,
        review_model=review_model,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        api_key=api_key or None,
        clear_api_key=clear_api_key,
    )
    echo_json(IntegrationConfigService().effective_config())


@llm_app.command("show-config")
def llm_show_config() -> None:
    ensure_db()
    echo_json(IntegrationConfigService().effective_config()["lmstudio"])


@llm_app.command("health")
def llm_health(json_output: bool = typer.Option(False, "--json", help="Print detailed JSON.")) -> None:
    health = LMStudioClient().health_detail()
    if json_output:
        echo_json({"ok": health.ok, "base_url": health.base_url, "models": health.models, "error": health.error})
        return
    typer.echo("ok" if health.ok else f"unavailable: {health.error}")


@llm_app.command("test-prompt")
def llm_test_prompt(prompt: str) -> None:
    result = LMStudioClient().chat(system_prompt="You are a concise card design assistant.", user_prompt=prompt)
    if not result.ok:
        typer.echo(f"ERROR: {result.error}")
        raise typer.Exit(1)
    typer.echo(result.text)


@comfy_app.command("configure")
def comfy_configure(
    base_url: str = typer.Option("http://127.0.0.1:8188", "--base-url", help="ComfyUI base URL."),
    input_dir: str = typer.Option(r"C:\ComfyUIInstall\input", "--input-dir", help="ComfyUI input directory."),
    output_dir: str = typer.Option(r"C:\ComfyUIInstall\output", "--output-dir", help="ComfyUI output directory."),
    timeout_seconds: float = typer.Option(1800.0, "--timeout-seconds", min=1.0),
    poll_interval_seconds: float = typer.Option(1.0, "--poll-interval-seconds", min=0.2),
    api_key: str = typer.Option("", "--api-key", help="Optional bearer token/API key."),
    clear_api_key: bool = typer.Option(False, "--clear-api-key", help="Remove saved ComfyUI API key."),
) -> None:
    """Persist ComfyUI network settings in workspace/config/integrations.json."""
    ensure_db()
    service = IntegrationConfigService()
    service.save_comfyui(
        base_url=base_url,
        input_dir=input_dir,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        api_key=api_key or None,
        clear_api_key=clear_api_key,
    )
    echo_json(IntegrationConfigService().effective_config())


@comfy_app.command("show-config")
def comfy_show_config() -> None:
    ensure_db()
    echo_json(IntegrationConfigService().effective_config()["comfyui"])


@comfy_app.command("health")
def comfy_health(json_output: bool = typer.Option(False, "--json", help="Print detailed JSON.")) -> None:
    health = ComfyClient().health_detail()
    if json_output:
        echo_json({"ok": health.ok, "base_url": health.base_url, "raw": health.raw, "error": health.error})
        return
    typer.echo("ok" if health.ok else f"unavailable: {health.error}")


@comfy_app.command("sync-workflows")
def comfy_sync_workflows() -> None:
    ensure_db()
    echo_json(WorkflowRegistryService().sync_defaults())


@comfy_app.command("workflows")
def comfy_workflows() -> None:
    ensure_db()
    echo_json({"workflows": WorkflowRegistryService().list_workflows()})


@comfy_app.command("validate-workflow")
def comfy_validate_workflow(workflow_key: str = "stub.card_art.t2i.v1") -> None:
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
    ensure_db()
    echo_json(
        ComfyArtService().prepare_card_art(
            project_slug,
            card_key,
            workflow_key=workflow_key,
            seed=seed,
            width=width,
            height=height,
            submit=False,
        )
    )
