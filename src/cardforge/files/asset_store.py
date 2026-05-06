from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cardforge.config import AppSettings, load_settings
from cardforge.domain.ids import validate_slug


class AssetStore:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        self.workspace_root = self.settings.workspace_root

    def ensure_workspace(self) -> Path:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "projects").mkdir(parents=True, exist_ok=True)
        return self.workspace_root

    def project_root(self, project_slug: str) -> Path:
        return self.workspace_root / "projects" / validate_slug(project_slug)

    def safe_resolve(self, path: str | Path) -> Path:
        raw = Path(path)
        resolved = raw if raw.is_absolute() else self.workspace_root / raw
        resolved = resolved.resolve()
        root = self.workspace_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Path escapes workspace: {path}") from exc
        return resolved

    def write_json(self, path: Path, payload: Any) -> None:
        target = self.safe_resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def read_json(self, path: Path) -> Any:
        target = self.safe_resolve(path)
        return json.loads(target.read_text(encoding="utf-8"))

    def write_text(self, path: Path, text: str) -> None:
        target = self.safe_resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def relative_to_workspace(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.workspace_root.resolve())).replace("\\", "/")
