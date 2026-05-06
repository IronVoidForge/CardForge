from __future__ import annotations

import json
from pathlib import Path

from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.defaults import (
    DEFAULT_CARD_TYPE_REGISTRY,
    DEFAULT_KEYWORD_REGISTRY,
    DEFAULT_PROMPT_FORMAT_MARKDOWN,
    DEFAULT_PROMPT_TEMPLATES,
    DEFAULT_TEMPLATE_REGISTRY,
    PROJECT_DIRS,
)

class ProjectScaffold:
    def __init__(self, asset_store: AssetStore | None = None) -> None:
        self.asset_store = asset_store or AssetStore()

    def create(self, project_slug: str, *, name: str = "") -> Path:
        self.asset_store.ensure_workspace()
        root = self.asset_store.project_root(project_slug)
        root.mkdir(parents=True, exist_ok=True)
        for rel in PROJECT_DIRS:
            (root / rel).mkdir(parents=True, exist_ok=True)
        self._write_if_missing(root / "project.json", {"slug": project_slug, "name": name or project_slug})
        self._write_if_missing(root / "card_type_registry.json", DEFAULT_CARD_TYPE_REGISTRY)
        self._write_if_missing(root / "keyword_registry.json", DEFAULT_KEYWORD_REGISTRY)
        self._write_if_missing(root / "template_registry.json", DEFAULT_TEMPLATE_REGISTRY)
        self._write_if_missing(root / "export_settings.json", {"default_formats": ["png", "json", "csv"]})
        self._write_prompt_templates(root)
        return root

    def _write_if_missing(self, path: Path, payload: dict) -> None:
        if path.exists():
            return
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


    def _write_prompt_templates(self, root: Path) -> None:
        prompt_root = root / "prompt_templates"
        prompt_root.mkdir(parents=True, exist_ok=True)
        format_path = prompt_root / "CARDFORGE_PROMPT_FORMAT.md"
        if not format_path.exists():
            format_path.write_text(DEFAULT_PROMPT_FORMAT_MARKDOWN, encoding="utf-8")
        registry = {
            "schema_version": "2026-05-prompt-template-registry-v1",
            "templates": {},
        }
        for template_key, markdown in DEFAULT_PROMPT_TEMPLATES.items():
            path = prompt_root / f"{template_key}.md"
            if not path.exists():
                path.write_text(markdown.strip() + "\n", encoding="utf-8")
            registry["templates"][template_key] = {
                "path": f"prompt_templates/{template_key}.md",
                "status": "active",
            }
        registry_path = root / "prompt_template_registry.json"
        if not registry_path.exists():
            registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
