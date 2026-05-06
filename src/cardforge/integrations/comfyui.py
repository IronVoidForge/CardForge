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


class ComfyClient:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.settings.comfy_base_url}/system_stats", timeout=5)
            return response.status_code < 500
        except Exception:  # pragma: no cover - manual integration path
            return False

    def submit_prompt(self, workflow_payload: dict[str, Any]) -> ComfySubmission:
        try:
            response = httpx.post(f"{self.settings.comfy_base_url}/prompt", json={"prompt": workflow_payload}, timeout=30)
            response.raise_for_status()
            raw = response.json()
            return ComfySubmission(ok=True, prompt_id=str(raw.get("prompt_id", "")), raw=raw)
        except Exception as exc:  # pragma: no cover - manual integration path
            return ComfySubmission(ok=False, error=str(exc))

    def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.comfy_timeout_seconds
        while time.monotonic() < deadline:  # pragma: no cover - manual integration path
            response = httpx.get(f"{self.settings.comfy_base_url}/history/{prompt_id}", timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get(prompt_id):
                return payload[prompt_id]
            time.sleep(1)
        raise TimeoutError(f"ComfyUI prompt timed out: {prompt_id}")
