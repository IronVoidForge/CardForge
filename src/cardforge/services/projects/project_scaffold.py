from __future__ import annotations

import json
from pathlib import Path

from cardforge.files.asset_store import AssetStore

PROJECT_DIRS = [
    "briefs",
    "batches",
    "cards",
    "templates/fronts",
    "templates/backs",
    "templates/frames",
    "templates/symbols",
    "exports/png",
    "exports/pdf",
    "exports/json",
    "exports/csv",
    "logs/llm",
    "logs/comfy",
    "logs/render",
    "logs/review",
]

DEFAULT_CARD_TYPE_REGISTRY = {
    "schema_version": "2026-05-card-type-registry-v1",
    "types": {
        "creature": {
            "display_name": "Creature",
            "required_fields": ["name", "cost", "type_line", "rules_text", "attack", "health", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "subtypes", "faction"],
            "template_id": "default_creature_front_v1",
            "allows_stats": True,
        },
        "spell": {
            "display_name": "Spell",
            "required_fields": ["name", "cost", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_spell_front_v1",
            "allows_stats": False,
        },
        "equipment": {
            "display_name": "Equipment",
            "required_fields": ["name", "cost", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_equipment_front_v1",
            "allows_stats": False,
        },
        "location": {
            "display_name": "Location",
            "required_fields": ["name", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_location_front_v1",
            "allows_stats": False,
        },
        "legendary": {
            "display_name": "Legendary",
            "required_fields": ["name", "cost", "type_line", "rules_text", "attack", "health", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "subtypes", "faction"],
            "template_id": "default_legendary_front_v1",
            "allows_stats": True,
        },
    },
}

DEFAULT_KEYWORD_REGISTRY = {
    "schema_version": "2026-05-keyword-registry-v1",
    "keywords": {
        "guard": {"display_name": "Guard", "rules_text": "This can block attacks against nearby allies."},
        "summon": {"display_name": "Summon", "rules_text": "Creates another unit or token."},
        "curse": {"display_name": "Curse", "rules_text": "Applies a negative ongoing effect."},
        "sacrifice": {"display_name": "Sacrifice", "rules_text": "Destroy or spend one of your own cards for value."},
        "graveyard": {"display_name": "Graveyard", "rules_text": "Interacts with discarded or destroyed cards."},
    },
}

DEFAULT_TEMPLATE_REGISTRY = {
    "schema_version": "2026-05-template-registry-v1",
    "templates": {
        "default_creature_front_v1": {"template_type": "front", "card_type": "creature"},
        "default_spell_front_v1": {"template_type": "front", "card_type": "spell"},
        "default_equipment_front_v1": {"template_type": "front", "card_type": "equipment"},
        "default_location_front_v1": {"template_type": "front", "card_type": "location"},
        "default_legendary_front_v1": {"template_type": "front", "card_type": "legendary"},
        "default_card_back_v1": {"template_type": "back", "card_type": "any"},
    },
}


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
        return root

    def _write_if_missing(self, path: Path, payload: dict) -> None:
        if path.exists():
            return
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
