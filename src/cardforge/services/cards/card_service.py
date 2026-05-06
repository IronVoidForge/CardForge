from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus
from cardforge.domain.ids import next_key, slugify
from cardforge.files.asset_store import AssetStore
from cardforge.schemas.card import CardCost, CardRecord, CardStats
from cardforge.schemas.card_batch import ParsedCardDraft
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
        type_line: str = "",
        keywords: list[str] | None = None,
        design_notes: str = "",
        template_id: str = "",
        batch_id: int | None = None,
        source: str = "manual_create",
    ) -> Row:
        draft = ParsedCardDraft(
            name=name,
            card_type=card_type,
            rarity=rarity,
            faction=faction,
            cost=cost,
            attack=attack,
            health=health,
            type_line=type_line,
            rules_text=rules_text,
            flavor_text=flavor_text,
            keywords=keywords or [],
            design_notes=design_notes,
            art_direction=art_direction,
            template_id=template_id,
        )
        with self.db.connection() as conn:
            return self.create_card_from_draft(
                project_slug,
                set_code,
                draft,
                batch_id=batch_id,
                source=source,
                review_description="New manually created card needs text review.",
                conn=conn,
            )

    def create_card_from_draft(
        self,
        project_slug: str,
        set_code: str,
        draft: ParsedCardDraft,
        *,
        batch_id: int | None = None,
        source: str = "generated",
        review_description: str = "Generated card needs text review.",
        conn: Connection | None = None,
    ) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            card_key = next_key(conn, "cards", "card_key", "CARD", where="set_id = ?", params=(set_row["id"],))
            base_slug = slugify(draft.name, fallback=card_key.lower())
            slug = self._dedupe_slug(conn, set_row["id"], base_slug)
            record = CardRecord(
                card_key=card_key,
                name=draft.name,
                slug=slug,
                card_type=draft.card_type.lower(),
                rarity=draft.rarity.lower(),
                faction=draft.faction,
                cost=CardCost(generic=draft.cost),
                stats=CardStats(attack=draft.attack, health=draft.health),
                type_line=draft.type_line,
                rules_text=draft.rules_text,
                flavor_text=draft.flavor_text,
                keywords=[item.strip().lower() for item in draft.keywords if str(item).strip()],
                design_notes=draft.design_notes,
                art_direction=draft.art_direction,
                template_id=draft.template_id,
            )
            conn.execute(
                """
                INSERT INTO cards(
                    set_id, batch_id, card_key, name, slug, card_type, type_line, rarity, faction, cost_json, stats_json,
                    rules_text, flavor_text, keywords_json, mechanics_json, design_notes, art_direction, template_id,
                    back_template_id, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    set_row["id"], batch_id, record.card_key, record.name, record.slug, record.card_type, record.type_line,
                    record.rarity, record.faction, record.cost.model_dump_json(), record.stats.model_dump_json(),
                    record.rules_text, record.flavor_text, json.dumps(record.keywords), json.dumps(record.mechanics),
                    record.design_notes, record.art_direction, record.template_id, record.back_template_id,
                    CardStatus.GENERATED.value if source != "manual_create" else CardStatus.DRAFT.value,
                ),
            )
            card = self.get_card(project_slug, card_key, conn=conn)
            version_id = self._append_version(conn, card, source=source, change_reason="Initial card creation", raw_payload=draft.raw)
            conn.execute("UPDATE cards SET current_version_id = ? WHERE id = ?", (version_id, card["id"]))
            card = self.get_card(project_slug, card_key, conn=conn)
            self._write_card_files(project_slug, card)
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=set_row["id"],
                target_type="card",
                target_id=card_key,
                review_type="card_text",
                title=f"Review card text: {draft.name}",
                description=review_description,
                metadata={"source": source, "batch_id": batch_id},
                conn=conn,
            )
            if close:
                conn.commit()
            return card
        finally:
            if close:
                conn.close()

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

    def list_versions(self, project_slug: str, card_key: str) -> list[Row]:
        with self.db.connection() as conn:
            card = self.get_card(project_slug, card_key, conn=conn)
            return list(conn.execute("SELECT * FROM card_versions WHERE card_id = ? ORDER BY version_number", (card["id"],)))

    def validate_card(self, project_slug: str, card_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            card = self.get_card(project_slug, card_key, conn=conn)
            report = self.validator.validate(project_slug, card)
            status = CardStatus.VALIDATED.value if report.valid else CardStatus.NEEDS_REPAIR.value
            conn.execute("UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, card["id"]))
            report_path = self.asset_store.project_root(project_slug) / "cards" / card_key / "validation_report.json"
            self.asset_store.write_json(report_path, report.model_dump())
            return report.model_dump()

    def update_card_fields(
        self,
        project_slug: str,
        card_key: str,
        *,
        source: str,
        change_reason: str,
        conn: Connection | None = None,
        **fields: Any,
    ) -> Row:
        allowed = {
            "name",
            "type_line",
            "rarity",
            "faction",
            "cost_json",
            "stats_json",
            "rules_text",
            "flavor_text",
            "keywords_json",
            "mechanics_json",
            "design_notes",
            "art_direction",
            "template_id",
            "status",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_card(project_slug, card_key, conn=conn)
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            card = self.get_card(project_slug, card_key, conn=conn)
            set_clauses = ", ".join(f"{key} = ?" for key in updates)
            values = list(updates.values())
            conn.execute(
                f"UPDATE cards SET {set_clauses}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*values, card["id"]),
            )
            updated = self.get_card(project_slug, card_key, conn=conn)
            version_id = self._append_version(conn, updated, source=source, change_reason=change_reason, raw_payload=updates)
            conn.execute("UPDATE cards SET current_version_id = ? WHERE id = ?", (version_id, updated["id"]))
            updated = self.get_card(project_slug, card_key, conn=conn)
            self._write_card_files(project_slug, updated)
            if close:
                conn.commit()
            return updated
        finally:
            if close:
                conn.close()

    def create_card_from_record(
        self,
        project_slug: str,
        set_code: str,
        record: CardRecord,
        *,
        batch_id: int | None = None,
        source: str = "generated",
        review_description: str = "Generated card needs text review.",
        conn: Connection | None = None,
    ) -> Row:
        draft = ParsedCardDraft(
            name=record.name,
            card_type=record.card_type,
            rarity=record.rarity,
            faction=record.faction,
            cost=record.cost.generic,
            attack=record.stats.attack,
            health=record.stats.health,
            type_line=record.type_line,
            rules_text=record.rules_text,
            flavor_text=record.flavor_text,
            keywords=record.keywords,
            design_notes=record.design_notes,
            art_direction=record.art_direction,
            template_id=record.template_id,
            raw=record.model_dump(),
        )
        return self.create_card_from_draft(
            project_slug,
            set_code,
            draft,
            batch_id=batch_id,
            source=source,
            review_description=review_description,
            conn=conn,
        )

    def update_card_text(
        self,
        project_slug: str,
        card_key: str,
        *,
        rules_text: str | None = None,
        flavor_text: str | None = None,
        design_notes: str | None = None,
        art_direction: str | None = None,
        source: str,
        change_reason: str,
    ) -> Row:
        updates: dict[str, Any] = {}
        if rules_text is not None:
            updates["rules_text"] = rules_text
        if flavor_text is not None:
            updates["flavor_text"] = flavor_text
        if design_notes is not None:
            updates["design_notes"] = design_notes
        if art_direction is not None:
            updates["art_direction"] = art_direction
        return self.update_card_fields(project_slug, card_key, source=source, change_reason=change_reason, **updates)

    def _append_version(
        self,
        conn: Connection,
        card: Row,
        *,
        source: str,
        change_reason: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> int:
        current = conn.execute("SELECT MAX(version_number) AS max_version FROM card_versions WHERE card_id = ?", (card["id"],)).fetchone()
        next_version = int(current["max_version"] or 0) + 1
        conn.execute(
            """
            INSERT INTO card_versions(
                card_id, version_number, source, name, type_line, cost_json, stats_json, rules_text,
                flavor_text, keywords_json, mechanics_json, design_notes, art_direction, change_reason, raw_payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["id"], next_version, source, card["name"], card["type_line"], card["cost_json"],
                card["stats_json"], card["rules_text"], card["flavor_text"], card["keywords_json"],
                card["mechanics_json"], card["design_notes"], card["art_direction"], change_reason,
                json.dumps(raw_payload or {}),
            ),
        )
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

    def _write_card_files(self, project_slug: str, card: Row) -> None:
        root = self.asset_store.project_root(project_slug) / "cards" / card["card_key"]
        payload = {key: card[key] for key in card.keys()}
        for json_field in ["cost_json", "stats_json", "keywords_json", "mechanics_json"]:
            target_key = json_field.removesuffix("_json")
            default = "[]" if json_field in {"keywords_json", "mechanics_json"} else "{}"
            payload[target_key] = json.loads(card[json_field] or default)
        self.asset_store.write_json(root / "card.json", payload)
        self.asset_store.write_text(root / "card.md", card_to_markdown(card))

    def _dedupe_slug(self, conn: Connection, set_id: int, base_slug: str) -> str:
        slug = base_slug
        index = 2
        while conn.execute("SELECT 1 FROM cards WHERE set_id = ? AND slug = ?", (set_id, slug)).fetchone():
            slug = f"{base_slug}_{index}"
            index += 1
        return slug
