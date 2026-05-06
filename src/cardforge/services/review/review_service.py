from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import ReviewDecision, ReviewStatus


class ReviewService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def enqueue(
        self,
        *,
        project_id: int,
        set_id: int | None,
        target_type: str,
        target_id: str,
        review_type: str,
        title: str,
        description: str = "",
        preview_path: str = "",
        severity: str = "normal",
        metadata: dict[str, Any] | None = None,
        conn: Connection | None = None,
    ) -> int:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            conn.execute(
                """
                INSERT INTO review_items(project_id, set_id, target_type, target_id, review_type, title, description, preview_path, severity, metadata_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, set_id, target_type, target_id, review_type, title, description, preview_path, severity, json.dumps(metadata or {})),
            )
            review_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
            if close:
                conn.commit()
            return review_id
        finally:
            if close:
                conn.close()

    def list_open(self, project_id: int) -> list[Row]:
        with self.db.connection() as conn:
            return list(conn.execute("SELECT * FROM review_items WHERE project_id = ? AND status = 'open' ORDER BY created_at", (project_id,)))

    def decide(self, review_item_id: int, *, decision: ReviewDecision, reason: str = "", tags: list[str] | None = None, notes: str = "") -> Row:
        status_by_decision = {
            ReviewDecision.APPROVE: ReviewStatus.APPROVED.value,
            ReviewDecision.REJECT: ReviewStatus.REJECTED.value,
            ReviewDecision.REQUEST_REWORK: ReviewStatus.NEEDS_REWORK.value,
            ReviewDecision.DEFER: ReviewStatus.OPEN.value,
            ReviewDecision.LOCK: ReviewStatus.RESOLVED.value,
            ReviewDecision.UNLOCK: ReviewStatus.OPEN.value,
        }
        with self.db.connection() as conn:
            item = conn.execute("SELECT * FROM review_items WHERE id = ?", (review_item_id,)).fetchone()
            if item is None:
                raise KeyError(f"Review item not found: {review_item_id}")
            conn.execute(
                """
                INSERT INTO review_decisions(review_item_id, target_type, target_id, decision, reason, tags_json, notes)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (review_item_id, item["target_type"], item["target_id"], decision.value, reason, json.dumps(tags or []), notes),
            )
            conn.execute(
                "UPDATE review_items SET status = ?, updated_at = CURRENT_TIMESTAMP, resolved_at = CASE WHEN ? != 'open' THEN CURRENT_TIMESTAMP ELSE resolved_at END WHERE id = ?",
                (status_by_decision[decision], status_by_decision[decision], review_item_id),
            )
            return conn.execute("SELECT * FROM review_items WHERE id = ?", (review_item_id,)).fetchone()
