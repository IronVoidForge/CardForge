from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cardforge.config import AppSettings, load_settings


SECRET_MASK = "********"


@dataclass(frozen=True)
class IntegrationConfigPaths:
    workspace_root: Path

    @property
    def config_dir(self) -> Path:
        return self.workspace_root / "config"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "integrations.json"


class IntegrationConfigService:
    """Persist local network integration settings outside source control.

    Environment variables still override values at runtime.  This service stores
    operator-friendly defaults for LAN/VPN LM Studio and ComfyUI instances.
    """

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        self.paths = IntegrationConfigPaths(self.settings.workspace_root)

    def load_raw(self) -> dict[str, Any]:
        if not self.paths.config_path.exists():
            return {}
        try:
            payload = json.loads(self.paths.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def effective_config(self) -> dict[str, Any]:
        current = load_settings()
        return {
            "config_path": str(self.paths.config_path),
            "lmstudio": {
                "base_url": current.lmstudio_base_url,
                "model": current.lmstudio_model,
                "review_model": current.lmstudio_review_model,
                "timeout_seconds": current.lmstudio_timeout_seconds,
                "max_tokens": current.lmstudio_max_tokens,
                "api_key_configured": bool(current.lmstudio_api_key),
            },
            "comfyui": {
                "base_url": current.comfy_base_url,
                "input_dir": str(current.comfy_input_dir),
                "output_dir": str(current.comfy_output_dir),
                "timeout_seconds": current.comfy_timeout_seconds,
                "poll_interval_seconds": current.comfy_poll_interval_seconds,
                "api_key_configured": bool(current.comfy_api_key),
            },
        }

    def masked_raw_config(self) -> dict[str, Any]:
        payload = self.load_raw()
        for section in ("lmstudio", "comfyui"):
            value = payload.get(section)
            if isinstance(value, dict) and value.get("api_key"):
                value["api_key"] = SECRET_MASK
        return payload

    def save_lmstudio(
        self,
        *,
        base_url: str,
        model: str,
        review_model: str,
        timeout_seconds: float,
        max_tokens: int | None,
        api_key: str | None = None,
        keep_existing_api_key: bool = True,
        clear_api_key: bool = False,
    ) -> dict[str, Any]:
        payload = self.load_raw()
        existing = payload.get("lmstudio", {}) if isinstance(payload.get("lmstudio"), dict) else {}
        section = {
            "base_url": base_url.strip().rstrip("/"),
            "model": model.strip(),
            "review_model": review_model.strip(),
            "timeout_seconds": max(1.0, float(timeout_seconds or 300.0)),
            "max_tokens": max_tokens if max_tokens and max_tokens > 0 else None,
        }
        if clear_api_key:
            pass
        elif api_key:
            section["api_key"] = api_key.strip()
        elif keep_existing_api_key and existing.get("api_key"):
            section["api_key"] = existing["api_key"]
        payload["lmstudio"] = section
        self._write(payload)
        return self.effective_config_from_payload(payload)

    def save_comfyui(
        self,
        *,
        base_url: str,
        input_dir: str,
        output_dir: str,
        timeout_seconds: float,
        poll_interval_seconds: float,
        api_key: str | None = None,
        keep_existing_api_key: bool = True,
        clear_api_key: bool = False,
    ) -> dict[str, Any]:
        payload = self.load_raw()
        existing = payload.get("comfyui", {}) if isinstance(payload.get("comfyui"), dict) else {}
        section = {
            "base_url": base_url.strip().rstrip("/"),
            "input_dir": input_dir.strip(),
            "output_dir": output_dir.strip(),
            "timeout_seconds": max(1.0, float(timeout_seconds or 1800.0)),
            "poll_interval_seconds": max(0.2, float(poll_interval_seconds or 1.0)),
        }
        if clear_api_key:
            pass
        elif api_key:
            section["api_key"] = api_key.strip()
        elif keep_existing_api_key and existing.get("api_key"):
            section["api_key"] = existing["api_key"]
        payload["comfyui"] = section
        self._write(payload)
        return self.effective_config_from_payload(payload)

    def effective_config_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        masked = json.loads(json.dumps(payload))
        for section in ("lmstudio", "comfyui"):
            value = masked.get(section)
            if isinstance(value, dict):
                value["api_key_configured"] = bool(value.get("api_key"))
                value.pop("api_key", None)
        return {"config_path": str(self.paths.config_path), **masked}

    def _write(self, payload: dict[str, Any]) -> None:
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.paths.config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
