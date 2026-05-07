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
    model: str = ""


@dataclass(frozen=True)
class LMStudioHealth:
    ok: bool
    base_url: str
    models: list[str]
    error: str = ""


class LMStudioClient:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> LMStudioResult:
        selected_model = model or self.settings.lmstudio_model
        payload: dict[str, Any] = {
            "model": selected_model,
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
                headers=self._headers(),
                timeout=self.settings.lmstudio_timeout_seconds,
            )
            response.raise_for_status()
            raw = response.json()
            text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
            return LMStudioResult(ok=True, text=str(text or ""), raw=raw, model=selected_model)
        except Exception as exc:  # pragma: no cover - manual integration path
            return LMStudioResult(ok=False, text="", raw={}, error=str(exc), model=selected_model)

    def health(self) -> bool:
        return self.health_detail().ok

    def health_detail(self) -> LMStudioHealth:
        try:
            response = httpx.get(f"{self.settings.lmstudio_base_url}/models", headers=self._headers(), timeout=5)
            response.raise_for_status()
            payload = response.json()
            models = [str(item.get("id", "")).strip() for item in payload.get("data", []) if isinstance(item, dict)]
            models = [item for item in models if item]
            return LMStudioHealth(ok=True, base_url=self.settings.lmstudio_base_url, models=models)
        except Exception as exc:  # pragma: no cover - manual integration path
            return LMStudioHealth(ok=False, base_url=self.settings.lmstudio_base_url, models=[], error=str(exc))

    def _headers(self) -> dict[str, str]:
        if not self.settings.lmstudio_api_key:
            return {}
        return {"Authorization": f"Bearer {self.settings.lmstudio_api_key}"}
