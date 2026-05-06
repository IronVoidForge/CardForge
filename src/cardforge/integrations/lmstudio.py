from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from cardforge.config import AppSettings, load_settings


@dataclass(frozen=True)
class LMStudioResult:
    ok: bool
    text: str
    raw: dict[str, Any]
    error: str = ""


class LMStudioClient:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def chat(self, *, system_prompt: str, user_prompt: str, model: str | None = None, temperature: float = 0.2) -> LMStudioResult:
        payload: dict[str, Any] = {
            "model": model or self.settings.lmstudio_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if self.settings.lmstudio_max_tokens is not None:
            payload["max_tokens"] = self.settings.lmstudio_max_tokens
        try:
            response = httpx.post(
                f"{self.settings.lmstudio_base_url}/chat/completions",
                json=payload,
                timeout=self.settings.lmstudio_timeout_seconds,
            )
            response.raise_for_status()
            raw = response.json()
            text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
            return LMStudioResult(ok=True, text=text, raw=raw)
        except Exception as exc:  # pragma: no cover - manual integration path
            return LMStudioResult(ok=False, text="", raw={}, error=str(exc))

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.settings.lmstudio_base_url}/models", timeout=5)
            return response.status_code < 500
        except Exception:  # pragma: no cover - manual integration path
            return False
