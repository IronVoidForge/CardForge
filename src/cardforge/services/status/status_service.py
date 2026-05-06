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
            project_id = project["id"]
            set_count = conn.execute("SELECT COUNT(*) AS n FROM sets WHERE project_id = ?", (project_id,)).fetchone()["n"]
            card_count = conn.execute("SELECT COUNT(*) AS n FROM cards c JOIN sets s ON s.id = c.set_id WHERE s.project_id = ?", (project_id,)).fetchone()["n"]
            batch_count = conn.execute("SELECT COUNT(*) AS n FROM card_batches b JOIN sets s ON s.id = b.set_id WHERE s.project_id = ?", (project_id,)).fetchone()["n"]
            open_reviews = conn.execute("SELECT COUNT(*) AS n FROM review_items WHERE project_id = ? AND status = 'open'", (project_id,)).fetchone()["n"]
            rendered = conn.execute("SELECT COUNT(*) AS n FROM renders r JOIN cards c ON c.id = r.card_id JOIN sets s ON s.id = c.set_id WHERE s.project_id = ?", (project_id,)).fetchone()["n"]
            art_candidates = conn.execute("SELECT COUNT(*) AS n FROM art_candidates ac JOIN cards c ON c.id = ac.card_id JOIN sets s ON s.id = c.set_id WHERE s.project_id = ?", (project_id,)).fetchone()["n"]
            locked_art = conn.execute("SELECT COUNT(*) AS n FROM art_candidates ac JOIN cards c ON c.id = ac.card_id JOIN sets s ON s.id = c.set_id WHERE s.project_id = ? AND ac.status = 'locked'", (project_id,)).fetchone()["n"]
            locked_cards = conn.execute("SELECT COUNT(*) AS n FROM cards c JOIN sets s ON s.id = c.set_id WHERE s.project_id = ? AND c.status = 'locked'", (project_id,)).fetchone()["n"]
            return {
                "project": {"slug": project["slug"], "name": project["name"], "status": project["status"], "root_path": project["root_path"]},
                "counts": {
                    "sets": set_count,
                    "batches": batch_count,
                    "cards": card_count,
                    "open_reviews": open_reviews,
                    "art_candidates": art_candidates,
                    "locked_art": locked_art,
                    "renders": rendered,
                    "locked_cards": locked_cards,
                },
                "next_action": self._next_action(card_count, batch_count, art_candidates, locked_art, rendered, open_reviews),
            }

    def _next_action(self, card_count: int, batch_count: int, art_candidates: int, locked_art: int, rendered: int, open_reviews: int) -> str:
        if card_count == 0:
            return "Generate a simulated batch or manually create cards."
        if batch_count and open_reviews:
            return "Review generated card text and validation issues."
        if art_candidates == 0:
            return "Generate dummy art candidates or connect ComfyUI for real art."
        if locked_art == 0:
            return "Approve and lock art candidates."
        if rendered == 0:
            return "Render cards using locked art or placeholder art."
        if open_reviews:
            return "Work through the review queue."
        return "Export locked or reviewed cards."
