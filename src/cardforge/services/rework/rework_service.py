from __future__ import annotations

import json
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService


class ReworkService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.cards = CardService(self.db)

    def create_request(
        self,
        project_slug: str,
        *,
        target_type: str,
        target_id: str,
        rework_type: str,
        reason: str = "",
        operator_notes: str = "",
        failure_tags: list[str] | None = None,
        source_review_item_id: int | None = None,
    ) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            conn.execute(
                """
                INSERT INTO rework_requests(project_id, source_review_item_id, target_type, target_id, rework_type, reason, operator_notes, failure_tags_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project["id"], source_review_item_id, target_type, target_id, rework_type, reason, operator_notes, json.dumps(failure_tags or [])),
            )
            rework_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
            return {"rework_id": rework_id, "target_type": target_type, "target_id": target_id, "rework_type": rework_type, "status": "requested"}

    def list_requests(self, project_slug: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            rows = conn.execute("SELECT * FROM rework_requests WHERE project_id = ? ORDER BY id", (project["id"],)).fetchall()
            return [{key: row[key] for key in row.keys()} for row in rows]
