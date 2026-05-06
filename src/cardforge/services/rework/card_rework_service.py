from __future__ import annotations

import json
from typing import Any

from cardforge.db.session import Database
from cardforge.services.cards.card_service import CardService
from cardforge.services.llm.offline_simulator import OfflineCardLLMSimulator
from cardforge.services.projects.project_service import ProjectService


class CardReworkService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.simulator = OfflineCardLLMSimulator()

    def repair_rules_text(
        self,
        project_slug: str,
        card_key: str,
        *,
        reason: str,
        source_review_item_id: int | None = None,
        failure_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            conn.execute(
                """
                INSERT INTO rework_requests(project_id, source_review_item_id, target_type, target_id, rework_type,
                                            reason, failure_tags_json, status)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project["id"], source_review_item_id, "card", card_key, "rules_text_repair",
                    reason, json.dumps(failure_tags or []), "running",
                ),
            )
            rework_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        repaired = self.simulator.repaired_rules_text(name=card["name"], original_rules=card["rules_text"], reason=reason)
        updated = self.cards.update_card_fields(
            project_slug,
            card_key,
            rules_text=repaired,
            source="offline_rules_repair",
            change_reason=f"Rules text repair: {reason}",
        )
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE rework_requests
                SET status = 'completed', result_target_type = 'card_version', result_target_id = ?,
                    updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(updated["current_version_id"]), rework_id),
            )
        return {"rework_id": rework_id, "card_key": card_key, "new_version_id": updated["current_version_id"], "rules_text": repaired}
