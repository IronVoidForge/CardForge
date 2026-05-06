from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus
from cardforge.domain.ids import next_key, slugify
from cardforge.files.asset_store import AssetStore
from cardforge.schemas.card import CardCost, CardRecord, CardStats
from cardforge.services.cards.card_markdown import card_to_markdown
from cardforge.services.cards.card_validation import CardValidationService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService


class CardService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.sets = SetService(self.db)
        self.validator = CardValidationService(self.asset_store)

    def create_card(
        self,
        project_slug: str,
        set_code: str,
        *,
        name: str,
        card_type: str,
        rules_text: str = "",
        rarity: str = "common",
        faction: str = "",
        attack: int | None = None,
        health: int | None = None,
        cost: int = 0,
        flavor_text: str = "",
        art_direction: str = "",
        source: str = "manual_create",
    ) -> Row:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            card_key = next_key(conn, "cards", "card_key", "CARD", where="set_id = ?", params=(set_row["id"],))
            base_slug = slugify(name, fallback=card_key.lower())
            slug = self._dedupe_slug(conn, set_row["id"], base_slug)
            record = CardRecord(
                card_key=card_key,
                name=name,
                slug=slug,
                card_type=card_type.lower(),
                rarity=rarity.lower(),
                faction=faction,
                cost=CardCost(generic=cost),
                stats=CardStats(attack=attack, health=health),
                rules_text=rules_text,
                flavor_text=flavor_text,
                art_direction=art_direction,
            )
            conn.execute(
                """
                INSERT INTO cards(
                    set_id, card_key, name, slug, card_type, type_line, rarity, faction, cost_json, stats_json,
                    rules_text, flavor_text, keywords_json, mechanics_json, design_notes, art_direction, template_id,
                    back_template_id, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    set_row["id"], record.card_key, record.name, record.slug, record.card_type, record.type_line,
                    record.rarity, record.faction, record.cost.model_dump_json(), record.stats.model_dump_json(),
                    record.rules_text, record.flavor_text, json.dumps(record.keywords), json.dumps(record.mechanics),
                    record.design_notes, record.art_direction, record.template_id, record.back_template_id,
                    CardStatus.DRAFT.value,
                ),
            )
            card = self.get_card(project_slug, card_key, conn=conn)
            version_id = self._append_version(conn, card, source=source, change_reason="Initial card creation")
            conn.execute("UPDATE cards SET current_version_id = ? WHERE id = ?", (version_id, card["id"]))
            card = self.get_card(project_slug, card_key, conn=conn)
            self._write_card_files(project_slug, card)
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=set_row["id"],
                target_type="card",
                target_id=card_key,
                review_type="card_text",
                title=f"Review card text: {name}",
                description="New manually created card needs text review.",
                conn=conn,
            )
            return card

    def get_card(self, project_slug: str, card_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                """
                SELECT c.* FROM cards c
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND c.card_key = ?
                """,
                (project["id"], card_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Card not found: {card_key}")
            return row
        finally:
            if close:
                conn.close()

    def list_cards(self, project_slug: str, set_code: str | None = None) -> list[Row]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            if set_code:
                set_row = self.sets.get_set(project_slug, set_code, conn=conn)
                return list(conn.execute("SELECT * FROM cards WHERE set_id = ? ORDER BY card_key", (set_row["id"],)))
            return list(conn.execute("SELECT c.* FROM cards c JOIN sets s ON s.id = c.set_id WHERE s.project_id = ? ORDER BY c.card_key", (project["id"],)))

    def validate_card(self, project_slug: str, card_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            card = self.get_card(project_slug, card_key, conn=conn)
            report = self.validator.validate(project_slug, card)
            status = CardStatus.VALIDATED.value if report.valid else CardStatus.NEEDS_REPAIR.value
            conn.execute("UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, card["id"]))
            report_path = self.asset_store.project_root(project_slug) / "cards" / card_key / "validation_report.json"
            self.asset_store.write_json(report_path, report.model_dump())
            return report.model_dump()

    def _append_version(self, conn: Connection, card: Row, *, source: str, change_reason: str = "") -> int:
        current = conn.execute("SELECT MAX(version_number) AS max_version FROM card_versions WHERE card_id = ?", (card["id"],)).fetchone()
        next_version = int(current["max_version"] or 0) + 1
        conn.execute(
            """
            INSERT INTO card_versions(
                card_id, version_number, source, name, type_line, cost_json, stats_json, rules_text,
                flavor_text, keywords_json, mechanics_json, design_notes, art_direction, change_reason
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["id"], next_version, source, card["name"], card["type_line"], card["cost_json"],
                card["stats_json"], card["rules_text"], card["flavor_text"], card["keywords_json"],
                card["mechanics_json"], card["design_notes"], card["art_direction"], change_reason,
            ),
        )
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

    def _write_card_files(self, project_slug: str, card: Row) -> None:
        root = self.asset_store.project_root(project_slug) / "cards" / card["card_key"]
        payload = {key: card[key] for key in card.keys()}
        for json_field in ["cost_json", "stats_json", "keywords_json", "mechanics_json"]:
            payload[json_field.removesuffix("_json")] = json.loads(card[json_field] or "{}" if json_field != "keywords_json" and json_field != "mechanics_json" else card[json_field] or "[]")
        self.asset_store.write_json(root / "card.json", payload)
        self.asset_store.write_text(root / "card.md", card_to_markdown(card))

    def _dedupe_slug(self, conn: Connection, set_id: int, base_slug: str) -> str:
        slug = base_slug
        index = 2
        while conn.execute("SELECT 1 FROM cards WHERE set_id = ? AND slug = ?", (set_id, slug)).fetchone():
            slug = f"{base_slug}_{index}"
            index += 1
        return slug
