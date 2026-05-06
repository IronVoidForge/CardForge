from __future__ import annotations

import json
import re
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService


AMBIGUOUS_PATTERNS = [
    (re.compile(r"\bthing\b|\bstuff\b", re.IGNORECASE), "Uses vague object wording."),
    (re.compile(r"\bany card\b", re.IGNORECASE), "'Any card' may need a target zone or type."),
    (re.compile(r"\bwhenever.*whenever\b", re.IGNORECASE), "Multiple trigger clauses may need simplification."),
    (re.compile(r"\bmay\b.*\bmay\b", re.IGNORECASE), "Repeated optional choices may slow play."),
]


class RulesReviewService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.batches = CardBatchService(self.db)
        self.projects = ProjectService(self.db)

    def review_batch(self, project_slug: str, batch_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            batch = self.batches.get_batch(project_slug, batch_key, conn=conn)
            cards = list(conn.execute("SELECT * FROM cards WHERE batch_id = ? ORDER BY card_key", (batch["id"],)))
            issues: list[dict[str, Any]] = []
            for card in cards:
                text = str(card["rules_text"] or "")
                for pattern, message in AMBIGUOUS_PATTERNS:
                    if pattern.search(text):
                        issues.append({"card_key": card["card_key"], "severity": "warning", "issue": message, "field": "rules_text"})
                if text and not text.endswith((".", "!", ")")):
                    issues.append({"card_key": card["card_key"], "severity": "warning", "issue": "Rules text should end cleanly with punctuation.", "field": "rules_text"})
            report = {"batch_key": batch_key, "issue_count": len(issues), "issues": issues, "status": "ok" if not issues else "needs_review"}
            batch_dir = self.asset_store.project_root(project_slug) / "batches" / batch_key
            self.asset_store.write_json(batch_dir / "rules_review_report.json", report)
            if issues:
                ReviewService(self.db).enqueue(
                    project_id=project["id"],
                    set_id=batch["set_id"],
                    target_type="batch",
                    target_id=batch_key,
                    review_type="rules_text",
                    title=f"Rules wording review: {batch_key}",
                    description=f"{len(issues)} possible wording issue(s) found.",
                    metadata=report,
                    conn=conn,
                )
            return report
