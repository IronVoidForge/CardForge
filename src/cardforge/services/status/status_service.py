from __future__ import annotations

from typing import Any

from cardforge.db.session import Database
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.resume.resume_service import ResumeService


class StatusService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.resume = ResumeService(self.db)

    def project_status(self, project_slug: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            project_id = int(project["id"])
            counts = {
                "sets": self._count(conn, "SELECT COUNT(*) FROM sets WHERE project_id = ?", project_id),
                "batches": self._count_project_join(conn, "card_batches", "b", project_id),
                "cards": self._count_cards(conn, project_id),
                "open_reviews": self._count(
                    conn,
                    "SELECT COUNT(*) FROM review_items WHERE project_id = ? AND status = 'open'",
                    project_id,
                ),
                "art_candidates": self._count_art(conn, project_id),
                "locked_art": self._count_art(conn, project_id, extra="AND ac.status = 'locked'"),
                "renders": self._count_renders(conn, project_id),
                "locked_cards": self._count(
                    conn,
                    """
                    SELECT COUNT(*) FROM cards c
                    JOIN sets s ON s.id = c.set_id
                    WHERE s.project_id = ? AND c.status = 'locked'
                    """,
                    project_id,
                ),
                "prompt_packages": self._count(
                    conn, "SELECT COUNT(*) FROM prompt_packages WHERE project_id = ?", project_id
                ),
                "auto_reviews": self._count(conn, "SELECT COUNT(*) FROM auto_reviews WHERE project_id = ?", project_id),
                "auto_needs_rework": self._count(
                    conn,
                    "SELECT COUNT(*) FROM auto_reviews WHERE project_id = ? AND auto_status = 'needs_rework'",
                    project_id,
                ),
                "jobs_pending": self._count(
                    conn,
                    "SELECT COUNT(*) FROM generation_jobs WHERE project_id = ? AND status = 'pending'",
                    project_id,
                ),
                "jobs_running": self._count(
                    conn,
                    "SELECT COUNT(*) FROM generation_jobs WHERE project_id = ? AND status = 'running'",
                    project_id,
                ),
                "jobs_failed": self._count(
                    conn,
                    "SELECT COUNT(*) FROM generation_jobs WHERE project_id = ? AND status = 'failed'",
                    project_id,
                ),
            }
        resume_plan = self.resume.plan_project(project_slug)
        return {
            "project": {
                "slug": project["slug"],
                "name": project["name"],
                "status": project["status"],
                "root_path": project["root_path"],
            },
            "counts": counts,
            "next_action": resume_plan["message"],
            "resume_plan": resume_plan,
        }

    def _count(self, conn: Any, sql: str, *params: Any) -> int:
        return int(conn.execute(sql, params).fetchone()[0])

    def _count_project_join(self, conn: Any, table: str, alias: str, project_id: int) -> int:
        return self._count(
            conn,
            f"""
            SELECT COUNT(*) FROM {table} {alias}
            JOIN sets s ON s.id = {alias}.set_id
            WHERE s.project_id = ?
            """,
            project_id,
        )

    def _count_cards(self, conn: Any, project_id: int) -> int:
        return self._count(
            conn,
            """
            SELECT COUNT(*) FROM cards c
            JOIN sets s ON s.id = c.set_id
            WHERE s.project_id = ?
            """,
            project_id,
        )

    def _count_art(self, conn: Any, project_id: int, *, extra: str = "") -> int:
        return self._count(
            conn,
            f"""
            SELECT COUNT(*) FROM art_candidates ac
            JOIN cards c ON c.id = ac.card_id
            JOIN sets s ON s.id = c.set_id
            WHERE s.project_id = ? {extra}
            """,
            project_id,
        )

    def _count_renders(self, conn: Any, project_id: int) -> int:
        return self._count(
            conn,
            """
            SELECT COUNT(*) FROM renders r
            JOIN cards c ON c.id = r.card_id
            JOIN sets s ON s.id = c.set_id
            WHERE s.project_id = ?
            """,
            project_id,
        )
