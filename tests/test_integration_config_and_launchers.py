from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cardforge.cli.main import app as cli_app
from cardforge.config import load_settings
from cardforge.services.integrations.integration_config_service import IntegrationConfigService
from cardforge.services.launchers.operator_launchers import write_operator_launchers
from cardforge.services.projects.project_service import ProjectService
from cardforge.web.app import create_app


def test_integration_config_persists_and_masks_secrets(workspace: Path) -> None:
    service = IntegrationConfigService()
    service.save_lmstudio(
        base_url="http://192.168.1.20:1234/v1/",
        model="gemma-card",
        review_model="qwen-review",
        timeout_seconds=120,
        max_tokens=4096,
        api_key="secret-llm",
    )
    service.save_comfyui(
        base_url="http://192.168.1.30:8188/",
        input_dir="D:/Comfy/input",
        output_dir="D:/Comfy/output",
        timeout_seconds=900,
        poll_interval_seconds=2,
        api_key="secret-comfy",
    )
    settings = load_settings()
    assert settings.lmstudio_base_url == "http://192.168.1.20:1234/v1"
    assert settings.lmstudio_model == "gemma-card"
    assert settings.lmstudio_api_key == "secret-llm"
    assert settings.comfy_base_url == "http://192.168.1.30:8188"
    assert settings.comfy_api_key == "secret-comfy"
    masked = service.masked_raw_config()
    assert masked["lmstudio"]["api_key"] == "********"
    assert masked["comfyui"]["api_key"] == "********"
    raw = json.loads((workspace / "config" / "integrations.json").read_text(encoding="utf-8"))
    assert raw["lmstudio"]["api_key"] == "secret-llm"


def test_integration_config_cli_round_trip(workspace: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "llm",
            "configure",
            "--base-url",
            "http://10.0.0.5:1234/v1",
            "--model",
            "card-model",
            "--review-model",
            "review-model",
        ],
    )
    assert result.exit_code == 0, result.output
    show = runner.invoke(cli_app, ["llm", "show-config"])
    assert show.exit_code == 0
    assert "card-model" in show.output
    assert (workspace / "config" / "integrations.json").exists()


def test_integration_settings_ui_can_save_values(db) -> None:  # type: ignore[no-untyped-def]
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/projects/gravebound_test/integrations/lmstudio/save",
            data={
                "base_url": "http://192.168.1.20:1234/v1",
                "model": "card-model",
                "review_model": "review-model",
                "timeout_seconds": "121",
                "max_tokens": "2048",
            },
            follow_redirects=True,
        )
    assert response.status_code == 200
    assert "card-model" in response.text
    assert "http://192.168.1.20:1234/v1" in response.text


def test_operator_launchers_write_scripts_and_mobile_html(workspace: Path) -> None:
    bundle = write_operator_launchers(host="192.168.1.42", port=8765)
    names = {path.name for path in bundle.files}
    assert "Start_CardForge_Both.bat" in names
    assert "Start_CardForge_Both.sh" in names
    assert "Open_CardForge_Mobile.html" in names
    assert bundle.mobile_url == "http://192.168.1.42:8765/m"
    html = (bundle.directory / "Open_CardForge_Mobile.html").read_text(encoding="utf-8")
    assert "192.168.1.42" in html
