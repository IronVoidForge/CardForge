from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any


class CardVersionService:
    """Append-only version writer for canonical card text and metadata snapshots."""

    def append_version(
        self,
        conn: Connection,
        card: Row,
        *,
        source: str,
        change_reason: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> int:
        current = conn.execute(
            "SELECT MAX(version_number) AS max_version FROM card_versions WHERE card_id = ?",
            (card["id"],),
        ).fetchone()
        next_version = int(current["max_version"] or 0) + 1
        conn.execute(
            """
            INSERT INTO card_versions(
                card_id, version_number, source, name, type_line, cost_json, stats_json, rules_text,
                flavor_text, keywords_json, mechanics_json, design_notes, art_direction, change_reason, raw_payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["id"],
                next_version,
                source,
                card["name"],
                card["type_line"],
                card["cost_json"],
                card["stats_json"],
                card["rules_text"],
                card["flavor_text"],
                card["keywords_json"],
                card["mechanics_json"],
                card["design_notes"],
                card["art_direction"],
                change_reason,
                json.dumps(raw_payload or {}, ensure_ascii=False),
            ),
        )
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
