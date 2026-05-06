from __future__ import annotations

from typing import Any

from cardforge.db.session import Database
from cardforge.services.projects.project_service import ProjectService


class StatusService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)

    def project_status(self, project_slug: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_count = conn.execute("SELECT COUNT(*) AS n FROM sets WHERE project_id = ?", (project["id"],)).fetchone()["n"]
            card_count = conn.execute("SELECT COUNT(*) AS n FROM cards c JOIN sets s ON s.id = c.set_id WHERE s.project_id = ?", (project["id"],)).fetchone()["n"]
            open_reviews = conn.execute("SELECT COUNT(*) AS n FROM review_items WHERE project_id = ? AND status = 'open'", (project["id"],)).fetchone()["n"]
            rendered = conn.execute("SELECT COUNT(*) AS n FROM renders r JOIN cards c ON c.id = r.card_id JOIN sets s ON s.id = c.set_id WHERE s.project_id = ?", (project["id"],)).fetchone()["n"]
            return {
                "project": {"slug": project["slug"], "name": project["name"], "status": project["status"], "root_path": project["root_path"]},
                "counts": {"sets": set_count, "cards": card_count, "open_reviews": open_reviews, "renders": rendered},
                "next_action": self._next_action(card_count, open_reviews, rendered),
            }

    def _next_action(self, card_count: int, open_reviews: int, rendered: int) -> str:
        if card_count == 0:
            return "Create a set and add or generate cards."
        if rendered == 0:
            return "Render cards with placeholder art or generated art."
        if open_reviews:
            return "Work through the review queue."
        return "Export locked or reviewed cards."
