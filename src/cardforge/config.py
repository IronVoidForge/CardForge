from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_integration_config(workspace: Path) -> dict[str, Any]:
    path = workspace / "config" / "integrations.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _section(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    return value if isinstance(value, dict) else {}


def _configured_value(
    payload: dict[str, Any],
    section: str,
    key: str,
    env_name: str,
    default: str,
) -> str:
    if env_name in os.environ:
        return os.environ.get(env_name, default)
    value = _section(payload, section).get(key)
    if value is None:
        return default
    return str(value)


def _configured_optional_value(payload: dict[str, Any], section: str, key: str, env_name: str) -> str | None:
    if env_name in os.environ:
        return os.environ.get(env_name) or None
    value = _section(payload, section).get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _configured_float(
    payload: dict[str, Any],
    section: str,
    key: str,
    env_name: str,
    default: float,
) -> float:
    raw = _configured_value(payload, section, key, env_name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _configured_int_or_none(payload: dict[str, Any], section: str, key: str, env_name: str) -> int | None:
    raw = _configured_optional_value(payload, section, key, env_name)
    if raw is None:
        return None
    raw = raw.strip()
    return int(raw) if raw.isdigit() else None


@dataclass(frozen=True)
class AppSettings:
    workspace_root: Path
    database_path: Path
    lmstudio_base_url: str
    lmstudio_model: str
    lmstudio_review_model: str
    lmstudio_timeout_seconds: float
    lmstudio_max_tokens: int | None
    lmstudio_api_key: str | None
    comfy_base_url: str
    comfy_input_dir: Path
    comfy_output_dir: Path
    comfy_timeout_seconds: float
    comfy_poll_interval_seconds: float
    comfy_api_key: str | None
    ui_require_auth: bool
    ui_password: str | None
    ui_session_secret: str
    ui_public_base_url: str | None
    ui_mobile_only: bool


def load_settings() -> AppSettings:
    workspace = Path(os.environ.get("CARDFORGE_WORKSPACE", "workspace")).expanduser().resolve()
    integration_config = _read_integration_config(workspace)
    db_path = Path(os.environ.get("CARDFORGE_DB_PATH", str(workspace / "cardforge.sqlite3"))).expanduser().resolve()
    password = os.environ.get("CARDFORGE_UI_PASSWORD") or None
    session_secret = os.environ.get("CARDFORGE_UI_SESSION_SECRET") or password or "cardforge-dev-only-secret"
    require_auth = _env_flag("CARDFORGE_UI_REQUIRE_AUTH", default=bool(password))
    lmstudio_base_url = _configured_value(
        integration_config,
        "lmstudio",
        "base_url",
        "CARDFORGE_LMSTUDIO_BASE_URL",
        "http://127.0.0.1:1234/v1",
    ).rstrip("/")
    comfy_base_url = _configured_value(
        integration_config,
        "comfyui",
        "base_url",
        "CARDFORGE_COMFY_BASE_URL",
        "http://127.0.0.1:8188",
    ).rstrip("/")
    return AppSettings(
        workspace_root=workspace,
        database_path=db_path,
        lmstudio_base_url=lmstudio_base_url,
        lmstudio_model=_configured_value(
            integration_config,
            "lmstudio",
            "model",
            "CARDFORGE_LMSTUDIO_MODEL",
            "local-cardforge-model",
        ),
        lmstudio_review_model=_configured_value(
            integration_config,
            "lmstudio",
            "review_model",
            "CARDFORGE_LMSTUDIO_REVIEW_MODEL",
            "local-cardforge-review-model",
        ),
        lmstudio_timeout_seconds=_configured_float(
            integration_config,
            "lmstudio",
            "timeout_seconds",
            "CARDFORGE_LMSTUDIO_TIMEOUT_SECONDS",
            300.0,
        ),
        lmstudio_max_tokens=_configured_int_or_none(
            integration_config,
            "lmstudio",
            "max_tokens",
            "CARDFORGE_LMSTUDIO_MAX_TOKENS",
        ),
        lmstudio_api_key=_configured_optional_value(
            integration_config,
            "lmstudio",
            "api_key",
            "CARDFORGE_LMSTUDIO_API_KEY",
        ),
        comfy_base_url=comfy_base_url,
        comfy_input_dir=Path(
            _configured_value(
                integration_config,
                "comfyui",
                "input_dir",
                "CARDFORGE_COMFY_INPUT_DIR",
                r"C:\ComfyUIInstall\input",
            )
        ),
        comfy_output_dir=Path(
            _configured_value(
                integration_config,
                "comfyui",
                "output_dir",
                "CARDFORGE_COMFY_OUTPUT_DIR",
                r"C:\ComfyUIInstall\output",
            )
        ),
        comfy_timeout_seconds=_configured_float(
            integration_config,
            "comfyui",
            "timeout_seconds",
            "CARDFORGE_COMFY_TIMEOUT_SECONDS",
            1800.0,
        ),
        comfy_poll_interval_seconds=_configured_float(
            integration_config,
            "comfyui",
            "poll_interval_seconds",
            "CARDFORGE_COMFY_POLL_INTERVAL_SECONDS",
            1.0,
        ),
        comfy_api_key=_configured_optional_value(
            integration_config,
            "comfyui",
            "api_key",
            "CARDFORGE_COMFY_API_KEY",
        ),
        ui_require_auth=require_auth,
        ui_password=password,
        ui_session_secret=session_secret,
        ui_public_base_url=os.environ.get("CARDFORGE_UI_PUBLIC_BASE_URL") or None,
        ui_mobile_only=_env_flag("CARDFORGE_UI_MOBILE_ONLY", default=False),
    )
