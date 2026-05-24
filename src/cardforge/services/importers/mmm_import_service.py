from __future__ import annotations

import json
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus
from cardforge.domain.ids import slugify
from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_file_writer import CardFileWriter
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService
from cardforge.services.templates.template_defaults import default_back_template, default_front_template
from cardforge.services.worksheets.worksheet_service import WorksheetService


class MMMImportService:
    """Import Magic, Math, & Monsters JSON into CardForge project/set/card state."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.sets = SetService(self.db)
        self.files = CardFileWriter(self.asset_store)
        self.worksheets = WorksheetService(self.db)

    def import_mmm(
        self,
        project_slug: str,
        *,
        project_name: str = "Magic, Math, & Monsters",
        project_description: str = "Imported Magic, Math, & Monsters production project.",
        player_deck_path: Path | None = None,
        loot_path: Path | None = None,
        monsters_path: Path | None = None,
        worksheets_path: Path | None = None,
        player_set_code: str = "PLAYER",
        monster_set_code: str = "MONSTER",
        create_project: bool = True,
        create_sets: bool = True,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        if not any([player_deck_path, loot_path, monsters_path, worksheets_path]):
            raise ValueError("Provide at least one MMM JSON file to import.")
        self._ensure_project(project_slug, project_name, project_description, create_project=create_project)
        self.ensure_mmm_registries(project_slug)
        self._ensure_dirs(project_slug)
        result: dict[str, Any] = {"project_slug": project_slug, "created_cards": [], "skipped_existing_cards": []}
        player_items = []
        if player_deck_path:
            player_items.extend(self._extract_items(self._read_json(player_deck_path), ("cards", "player_cards")))
        if loot_path:
            player_items.extend(self._extract_items(self._read_json(loot_path), ("loot_insert_cards", "loot", "cards")))
        if player_items:
            self._ensure_set(project_slug, player_set_code, "MMM Player Deck", len(player_items), create_sets=create_sets)
            if replace_existing:
                self._delete_set_cards(project_slug, player_set_code)
            for item in player_items:
                mapped = self._map_loot(item) if str(item.get("id", "")).startswith("LOOT") else self._map_player(item)
                created = self._create_or_skip(project_slug, player_set_code, mapped, skip_existing=not replace_existing)
                result["created_cards" if created else "skipped_existing_cards"].append(mapped["card_key"])
        monster_items = []
        if monsters_path:
            monster_items.extend(self._extract_items(self._read_json(monsters_path), ("monster_cards", "monsters", "cards")))
        if monster_items:
            self._ensure_set(project_slug, monster_set_code, "MMM Monster Deck", len(monster_items), create_sets=create_sets)
            if replace_existing:
                self._delete_set_cards(project_slug, monster_set_code)
            for item in monster_items:
                mapped = self._map_monster(item)
                created = self._create_or_skip(project_slug, monster_set_code, mapped, skip_existing=not replace_existing)
                result["created_cards" if created else "skipped_existing_cards"].append(mapped["card_key"])
        if worksheets_path:
            result["worksheets"] = self.worksheets.import_worksheets(project_slug, worksheets_path, replace_existing=replace_existing)
        result["created_card_count"] = len(result["created_cards"])
        result["skipped_existing_card_count"] = len(result["skipped_existing_cards"])
        manifest = self.asset_store.project_root(project_slug) / "imports" / "mmm_import_manifest.json"
        self.asset_store.write_json(manifest, result)
        result["manifest_path"] = self.asset_store.relative_to_workspace(manifest)
        return result

    def ensure_mmm_registries(self, project_slug: str) -> dict[str, Any]:
        root = self.asset_store.project_root(project_slug)
        card_type_path = root / "card_type_registry.json"
        template_path = root / "template_registry.json"
        card_types = self._read_json_if_exists(card_type_path) or {"types": {}}
        card_types.setdefault("schema_version", "2026-05-card-type-registry-v1")
        types = card_types.setdefault("types", {})
        for type_key, display, template, stats in [
            ("mmm_player_spell", "MMM Player Spell", "mmm_player_spell_front_v1", False),
            ("mmm_player_loot", "MMM Player Loot", "mmm_player_loot_front_v1", False),
            ("mmm_monster", "MMM Monster", "mmm_monster_front_v1", True),
        ]:
            types[type_key] = {
                "display_name": display,
                "required_fields": ["name", "type_line", "rules_text", "rarity"],
                "optional_fields": ["flavor_text", "faction"],
                "template_id": template,
                "allows_stats": stats,
            }
        self.asset_store.write_json(card_type_path, card_types)
        templates = self._read_json_if_exists(template_path) or {"templates": {}}
        registry = templates.setdefault("templates", {})
        for key, base_type in [("mmm_player_spell_front_v1", "spell"), ("mmm_player_loot_front_v1", "equipment"), ("mmm_monster_front_v1", "creature")]:
            template = default_front_template(key, base_type)
            template["name"] = key.replace("_", " ").title()
            registry[key] = template
        for key, label in [("mmm_player_back_v1", "Magic, Math, & Monsters Player Deck"), ("mmm_monster_back_v1", "Magic, Math, & Monsters Monster Deck")]:
            template = default_back_template()
            template["template_key"] = key
            template["name"] = label
            registry[key] = template
        self.asset_store.write_json(template_path, templates)
        return {"card_type_count": len(types), "template_count": len(registry)}

    def _create_or_skip(self, project_slug: str, set_code: str, data: dict[str, Any], *, skip_existing: bool) -> bool:
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            existing = conn.execute("SELECT * FROM cards WHERE set_id = ? AND card_key = ?", (set_row["id"], data["card_key"])).fetchone()
            if existing and skip_existing:
                return False
            if existing:
                conn.execute("DELETE FROM cards WHERE id = ?", (existing["id"],))
            self._insert_card(conn, project_slug, set_row["id"], data)
            return True

    def _insert_card(self, conn: Connection, project_slug: str, set_id: int, data: dict[str, Any]) -> None:
        slug = self._dedupe_slug(conn, set_id, slugify(data["name"], fallback=data["card_key"].lower()))
        cost_json = json.dumps({"generic": data.get("cost", 0), "display": str(data.get("cost", 0))})
        stats_json = json.dumps({"attack": data.get("attack"), "health": data.get("health")})
        mechanics_json = json.dumps(data.get("mechanics", []), ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO cards(set_id, card_key, name, slug, card_number, card_type, type_line, rarity, faction, cost_json, stats_json, rules_text, flavor_text, keywords_json, mechanics_json, design_notes, art_direction, template_id, back_template_id, status)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, '[]', ?, '', ?, ?, ?, ?)
            """,
            (set_id, data["card_key"], data["name"], slug, data["card_key"], data["card_type"], data["type_line"], data["rarity"], cost_json, stats_json, data["rules_text"], data["flavor_text"], mechanics_json, data["art_direction"], data["template_id"], data["back_template_id"], CardStatus.DRAFT.value),
        )
        card = conn.execute("SELECT * FROM cards WHERE set_id = ? AND card_key = ?", (set_id, data["card_key"])).fetchone()
        conn.execute(
            """
            INSERT INTO card_versions(card_id, version_number, source, name, type_line, cost_json, stats_json, rules_text, flavor_text, keywords_json, mechanics_json, design_notes, art_direction, change_reason, raw_payload_json)
            VALUES(?, 1, 'mmm_import', ?, ?, ?, ?, ?, ?, '[]', ?, '', ?, 'Initial MMM import', ?)
            """,
            (card["id"], data["name"], data["type_line"], cost_json, stats_json, data["rules_text"], data["flavor_text"], mechanics_json, data["art_direction"], json.dumps(data, ensure_ascii=False)),
        )
        version = conn.execute("SELECT id FROM card_versions WHERE card_id = ?", (card["id"],)).fetchone()
        conn.execute("UPDATE cards SET current_version_id = ? WHERE id = ?", (version["id"], card["id"]))
        card = conn.execute("SELECT * FROM cards WHERE id = ?", (card["id"],)).fetchone()
        self.files.write_card_files(project_slug, card)

    def _map_player(self, item: dict[str, Any]) -> dict[str, Any]:
        cid = str(item.get("id") or item.get("card_id") or item.get("title") or "PLY-UNKNOWN")
        title = str(item.get("title") or item.get("name") or cid)
        front = item.get("front_text") or {}
        guide = item.get("guide_data") or {}
        math = item.get("math") or {}
        dodge = item.get("quick_dodge") or item.get("dodge_rune") or {}
        rules = self._join([front.get("problem") or item.get("problem"), front.get("solve_path") or item.get("solve_path"), f"Answer: {guide.get('equation') or guide.get('answer') or item.get('answer', '')}".strip()])
        flavor = self._join([front.get("flavor"), f"Quick Dodge: {dodge.get('prompt', '')}" if dodge else ""])
        return {"card_key": cid, "name": title, "card_type": "mmm_player_spell", "type_line": f"MMM Player Spell - {item.get('rank_icon') or item.get('deck') or math.get('skill_category', 'Math')}", "rarity": "common", "cost": 0, "attack": None, "health": None, "rules_text": rules, "flavor_text": flavor, "art_direction": self._art(item), "template_id": "mmm_player_spell_front_v1", "back_template_id": "mmm_player_back_v1", "mechanics": [{"source": "magic_math_monsters", "raw": item}]}

    def _map_loot(self, item: dict[str, Any]) -> dict[str, Any]:
        cid = str(item.get("id") or item.get("card_id") or item.get("title") or "LOOT-UNKNOWN")
        title = str(item.get("title") or item.get("name") or cid)
        rules = self._join([item.get("effect"), item.get("activation_puzzle"), item.get("rules_text")])
        return {"card_key": cid, "name": title, "card_type": "mmm_player_loot", "type_line": "MMM Loot Insert", "rarity": "common", "cost": 0, "attack": None, "health": None, "rules_text": rules, "flavor_text": str(item.get("flavor_text") or item.get("story_text") or ""), "art_direction": self._art(item), "template_id": "mmm_player_loot_front_v1", "back_template_id": "mmm_player_back_v1", "mechanics": [{"source": "magic_math_monsters", "raw": item}]}

    def _map_monster(self, item: dict[str, Any]) -> dict[str, Any]:
        cid = str(item.get("id") or item.get("card_id") or item.get("name") or "MON-UNKNOWN")
        title = str(item.get("name") or item.get("title") or cid)
        hp = item.get("hp", {})
        base_hp = hp.get("base") if isinstance(hp, dict) else hp
        attack = item.get("attack", {})
        damage = attack.get("damage") if isinstance(attack, dict) else None
        ability = item.get("special_ability") or {}
        rules = self._join([f"HP: {base_hp}" if base_hp is not None else "", f"Attack: {attack.get('name', 'Monster Attack')} - {damage} damage" if isinstance(attack, dict) and damage is not None else "", f"Ability: {ability.get('name', '')}. {ability.get('rules_text', '')}" if ability else item.get("rules_text")])
        return {"card_key": cid, "name": title, "card_type": "mmm_monster", "type_line": str(item.get("monster_type") or item.get("type_line") or "MMM Monster"), "rarity": "common", "cost": 0, "attack": int(damage) if str(damage or "").isdigit() else None, "health": int(base_hp) if str(base_hp or "").isdigit() else None, "rules_text": rules, "flavor_text": str(item.get("story_role") or item.get("defeat_text") or ""), "art_direction": self._art(item), "template_id": "mmm_monster_front_v1", "back_template_id": "mmm_monster_back_v1", "mechanics": [{"source": "magic_math_monsters", "raw": item}]}

    def _ensure_project(self, project_slug: str, name: str, description: str, *, create_project: bool) -> None:
        try:
            self.projects.get_project(project_slug)
        except KeyError:
            if not create_project:
                raise
            self.projects.create_project(project_slug, name=name, description=description)

    def _ensure_set(self, project_slug: str, set_code: str, name: str, count: int, *, create_sets: bool) -> None:
        try:
            self.sets.get_set(project_slug, set_code)
            return
        except KeyError:
            if not create_sets:
                raise
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            conn.execute("INSERT INTO sets(project_id, set_code, name, description, game_mode, target_card_count) VALUES(?, ?, ?, ?, ?, ?)", (project["id"], set_code, name, "Imported from Magic, Math, & Monsters JSON.", "magic_math_monsters", count))

    def _delete_set_cards(self, project_slug: str, set_code: str) -> None:
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            conn.execute("DELETE FROM cards WHERE set_id = ?", (set_row["id"],))

    def _ensure_dirs(self, project_slug: str) -> None:
        root = self.asset_store.project_root(project_slug)
        for rel in ["imports", "worksheets/json", "worksheets/renders", "exports/print_sheets", "exports/game_package"]:
            (root / rel).mkdir(parents=True, exist_ok=True)

    def _extract_items(self, payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload] if payload.get("id") or payload.get("name") or payload.get("title") else []

    def _read_json(self, path: Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        raise ValueError(f"Expected JSON object/list at {path}")

    def _read_json_if_exists(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _dedupe_slug(self, conn: Connection, set_id: int, base: str) -> str:
        slug = base
        index = 2
        while conn.execute("SELECT 1 FROM cards WHERE set_id = ? AND slug = ?", (set_id, slug)).fetchone():
            slug = f"{base}_{index}"
            index += 1
        return slug

    def _art(self, item: dict[str, Any]) -> str:
        art = item.get("art") or {}
        if isinstance(art, dict):
            return str(art.get("art_window_prompt") or art.get("prompt") or art.get("worksheet_art_prompt") or "")
        return str(item.get("art_direction") or item.get("art_prompt") or "")

    def _join(self, parts: list[Any]) -> str:
        return "\n".join(str(item).strip() for item in parts if str(item or "").strip())
