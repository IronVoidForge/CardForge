from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    workspace_root: Path
    database_path: Path
    lmstudio_base_url: str
    lmstudio_model: str
    lmstudio_review_model: str
    lmstudio_timeout_seconds: float
    lmstudio_max_tokens: int | None
    comfy_base_url: str
    comfy_input_dir: Path
    comfy_output_dir: Path
    comfy_timeout_seconds: float
    ui_require_auth: bool
    ui_password: str | None
    ui_session_secret: str
    ui_public_base_url: str | None
    ui_mobile_only: bool


def load_settings() -> AppSettings:
    workspace = Path(os.environ.get("CARDFORGE_WORKSPACE", "workspace")).expanduser().resolve()
    db_path = Path(os.environ.get("CARDFORGE_DB_PATH", str(workspace / "cardforge.sqlite3"))).expanduser().resolve()
    max_tokens_raw = os.environ.get("CARDFORGE_LMSTUDIO_MAX_TOKENS", "").strip()
    password = os.environ.get("CARDFORGE_UI_PASSWORD") or None
    session_secret = os.environ.get("CARDFORGE_UI_SESSION_SECRET") or password or "cardforge-dev-only-secret"
    require_auth = _env_flag("CARDFORGE_UI_REQUIRE_AUTH", default=bool(password))
    return AppSettings(
        workspace_root=workspace,
        database_path=db_path,
        lmstudio_base_url=os.environ.get("CARDFORGE_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/"),
        lmstudio_model=os.environ.get("CARDFORGE_LMSTUDIO_MODEL", "local-cardforge-model"),
        lmstudio_review_model=os.environ.get("CARDFORGE_LMSTUDIO_REVIEW_MODEL", "local-cardforge-review-model"),
        lmstudio_timeout_seconds=float(os.environ.get("CARDFORGE_LMSTUDIO_TIMEOUT_SECONDS", "300")),
        lmstudio_max_tokens=int(max_tokens_raw) if max_tokens_raw.isdigit() else None,
        comfy_base_url=os.environ.get("CARDFORGE_COMFY_BASE_URL", "http://127.0.0.1:8188").rstrip("/"),
        comfy_input_dir=Path(os.environ.get("CARDFORGE_COMFY_INPUT_DIR", r"C:\ComfyUIInstall\input")),
        comfy_output_dir=Path(os.environ.get("CARDFORGE_COMFY_OUTPUT_DIR", r"C:\ComfyUIInstall\output")),
        comfy_timeout_seconds=float(os.environ.get("CARDFORGE_COMFY_TIMEOUT_SECONDS", "1800")),
        ui_require_auth=require_auth,
        ui_password=password,
        ui_session_secret=session_secret,
        ui_public_base_url=os.environ.get("CARDFORGE_UI_PUBLIC_BASE_URL") or None,
        ui_mobile_only=_env_flag("CARDFORGE_UI_MOBILE_ONLY", default=False),
    )
