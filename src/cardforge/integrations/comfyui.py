from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from cardforge.config import AppSettings, load_settings


@dataclass(frozen=True)
class ComfySubmission:
    ok: bool
    prompt_id: str = ""
    raw: dict[str, Any] | None = None
    error: str = ""


@dataclass(frozen=True)
class ComfyHealth:
    ok: bool
    base_url: str
    raw: dict[str, Any] | None = None
    error: str = ""


class ComfyClient:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def health(self) -> bool:
        return self.health_detail().ok

    def health_detail(self) -> ComfyHealth:
        try:
            response = httpx.get(f"{self.settings.comfy_base_url}/system_stats", headers=self._headers(), timeout=5)
            response.raise_for_status()
            return ComfyHealth(ok=True, base_url=self.settings.comfy_base_url, raw=response.json())
        except Exception as exc:  # pragma: no cover - manual integration path
            return ComfyHealth(ok=False, base_url=self.settings.comfy_base_url, error=str(exc))

    def submit_prompt(self, workflow_payload: dict[str, Any]) -> ComfySubmission:
        try:
            response = httpx.post(
                f"{self.settings.comfy_base_url}/prompt",
                json={"prompt": workflow_payload},
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json()
            return ComfySubmission(ok=True, prompt_id=str(raw.get("prompt_id", "")), raw=raw)
        except Exception as exc:  # pragma: no cover - manual integration path
            return ComfySubmission(ok=False, error=str(exc))

    def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.comfy_timeout_seconds
        while time.monotonic() < deadline:  # pragma: no cover - manual integration path
            response = httpx.get(f"{self.settings.comfy_base_url}/history/{prompt_id}", headers=self._headers(), timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get(prompt_id):
                return payload[prompt_id]
            time.sleep(self.settings.comfy_poll_interval_seconds)
        raise TimeoutError(f"ComfyUI prompt timed out: {prompt_id}")

    def _headers(self) -> dict[str, str]:
        if not self.settings.comfy_api_key:
            return {}
        return {"Authorization": f"Bearer {self.settings.comfy_api_key}"}
