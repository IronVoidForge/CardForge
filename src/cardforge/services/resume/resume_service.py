from __future__ import annotations

from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import JobType, ResumeActionType
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService


class ResumeService:
    """Plan the next safe operator action for a project/set.

    This intentionally returns recommendations instead of mutating state. The UI
    and CLI can turn recommendations into queued jobs when the operator chooses.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.sets = SetService(self.db)

    def plan_project(self, project_slug: str, set_code: str | None = None) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_row = self._select_set(project_slug, set_code, conn)
            project_id = int(project["id"])
            if set_row is None:
                return self._plan_no_set(project_slug)

            set_id = int(set_row["id"])
            cards = conn.execute("SELECT * FROM cards WHERE set_id = ? ORDER BY card_key", (set_id,)).fetchall()
            batch_count = conn.execute("SELECT COUNT(*) AS n FROM card_batches WHERE set_id = ?", (set_id,)).fetchone()["n"]
            pending_jobs = conn.execute(
                "SELECT COUNT(*) AS n FROM generation_jobs WHERE project_id = ? AND status IN ('pending', 'running')",
                (project_id,),
            ).fetchone()["n"]
            open_reviews = conn.execute(
                "SELECT COUNT(*) AS n FROM review_items WHERE project_id = ? AND status = 'open'",
                (project_id,),
            ).fetchone()["n"]
            needs_rework = conn.execute(
                "SELECT COUNT(*) AS n FROM auto_reviews WHERE project_id = ? AND auto_status = 'needs_rework'",
                (project_id,),
            ).fetchone()["n"]
            locked_art_count = conn.execute(
                """
                SELECT COUNT(*) AS n FROM art_candidates ac
                JOIN cards c ON c.id = ac.card_id
                WHERE c.set_id = ? AND ac.status = 'locked'
                """,
                (set_id,),
            ).fetchone()["n"]
            rendered_count = conn.execute(
                """
                SELECT COUNT(DISTINCT c.id) AS n FROM cards c
                JOIN renders r ON r.card_id = c.id
                WHERE c.set_id = ?
                """,
                (set_id,),
            ).fetchone()["n"]
            export_count = conn.execute("SELECT COUNT(*) AS n FROM exports WHERE set_id = ?", (set_id,)).fetchone()["n"]
            cards_missing_art = [row["card_key"] for row in cards if not self._has_locked_art(conn, int(row["id"]))]
            cards_missing_render = [row["card_key"] for row in cards if not self._has_render(conn, int(row["id"]))]

            if pending_jobs:
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.NONE,
                    "Run or inspect queued jobs before creating more work.",
                    blockers=[],
                    suggested_jobs=[],
                    metrics={"pending_or_running_jobs": pending_jobs},
                )
            if not cards:
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.GENERATE_BATCH,
                    "Generate the first card batch.",
                    suggested_jobs=[
                        {
                            "job_type": JobType.BATCH_GENERATE.value,
                            "target_type": "set",
                            "target_id": set_row["set_code"],
                            "payload": {
                                "set_code": set_row["set_code"],
                                "count": max(1, int(set_row["target_card_count"] or 12)),
                                "request_text": "Generate a balanced prototype card batch.",
                                "use_mock": True,
                            },
                        }
                    ],
                    metrics={"batch_count": batch_count},
                )
            if needs_rework:
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.RESOLVE_AUTO_REVIEW,
                    "Resolve cards or art flagged by auto-review.",
                    blockers=["auto_review_needs_rework"],
                    suggested_jobs=[],
                    metrics={"needs_rework": needs_rework},
                )
            if open_reviews:
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.REVIEW_QUEUE,
                    "Work through the open review queue.",
                    blockers=["open_reviews"],
                    suggested_jobs=[],
                    metrics={"open_reviews": open_reviews},
                )
            if cards_missing_art:
                card_key = cards_missing_art[0]
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.GENERATE_ART,
                    f"Generate or lock art for {len(cards_missing_art)} card(s).",
                    suggested_jobs=[
                        {
                            "job_type": JobType.ART_GENERATE_DUMMY.value,
                            "target_type": "card",
                            "target_id": card_key,
                            "payload": {"card_key": card_key, "count": 4},
                        }
                    ],
                    metrics={"cards_missing_art": len(cards_missing_art), "locked_art_count": locked_art_count},
                )
            if cards_missing_render:
                card_key = cards_missing_render[0]
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.RENDER_CARDS,
                    f"Render {len(cards_missing_render)} card(s).",
                    suggested_jobs=[
                        {
                            "job_type": JobType.RENDER_CARD.value,
                            "target_type": "card",
                            "target_id": card_key,
                            "payload": {"card_key": card_key, "placeholder_art": False},
                        }
                    ],
                    metrics={"cards_missing_render": len(cards_missing_render), "rendered_count": rendered_count},
                )
            if not export_count:
                return self._plan(
                    project_slug,
                    set_row["set_code"],
                    ResumeActionType.EXPORT,
                    "Export the set.",
                    suggested_jobs=[
                        {
                            "job_type": JobType.EXPORT_JSON.value,
                            "target_type": "set",
                            "target_id": set_row["set_code"],
                            "payload": {"set_code": set_row["set_code"]},
                        }
                    ],
                    metrics={"rendered_count": rendered_count},
                )
            return self._plan(
                project_slug,
                set_row["set_code"],
                ResumeActionType.NONE,
                "Project is ready. Continue polishing, exporting, or creating another batch.",
                metrics={"card_count": len(cards), "exports": export_count},
            )

    def _select_set(self, project_slug: str, set_code: str | None, conn: Any) -> Any | None:
        if set_code:
            return self.sets.get_set(project_slug, set_code, conn=conn)
        project = self.projects.get_project(project_slug, conn=conn)
        return conn.execute(
            "SELECT * FROM sets WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (project["id"],),
        ).fetchone()

    def _plan_no_set(self, project_slug: str) -> dict[str, Any]:
        return self._plan(
            project_slug,
            None,
            ResumeActionType.NONE,
            "Create a set before generating cards.",
            blockers=["no_set"],
            suggested_jobs=[],
        )

    def _has_locked_art(self, conn: Any, card_id: int) -> bool:
        return bool(
            conn.execute(
                "SELECT 1 FROM art_candidates WHERE card_id = ? AND status = 'locked' LIMIT 1",
                (card_id,),
            ).fetchone()
        )

    def _has_render(self, conn: Any, card_id: int) -> bool:
        return bool(conn.execute("SELECT 1 FROM renders WHERE card_id = ? LIMIT 1", (card_id,)).fetchone())

    def _plan(
        self,
        project_slug: str,
        set_code: str | None,
        action_type: ResumeActionType,
        message: str,
        *,
        blockers: list[str] | None = None,
        suggested_jobs: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "project_slug": project_slug,
            "set_code": set_code,
            "action_type": action_type.value,
            "message": message,
            "blockers": blockers or [],
            "suggested_jobs": suggested_jobs or [],
            "metrics": metrics or {},
        }
