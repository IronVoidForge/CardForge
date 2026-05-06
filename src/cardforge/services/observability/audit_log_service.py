from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any

from cardforge.db.session import Database


class AuditLogService:
    """Append-only audit trail for operator and worker actions."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def record(
        self,
        conn: Connection,
        *,
        project_id: int | None,
        event_type: str,
        target_type: str = "",
        target_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> int:
        conn.execute(
            """
            INSERT INTO audit_events(project_id, event_type, target_type, target_id, payload_json)
            VALUES(?, ?, ?, ?, ?)
            """,
            (project_id, event_type, target_type, target_id, json.dumps(payload or {}, ensure_ascii=False)),
        )
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

    def list_recent(self, project_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(500, int(limit)))
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_events
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            return [self._to_dict(row) for row in rows]

    def _to_dict(self, row: Any) -> dict[str, Any]:
        payload = {key: row[key] for key in row.keys()}
        try:
            payload["payload"] = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload["payload"] = {}
        return payload
