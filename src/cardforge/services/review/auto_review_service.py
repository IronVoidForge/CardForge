from __future__ import annotations

import json
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.review.auto_review_heuristics import HeuristicAutoReviewer
from cardforge.services.review.auto_review_report_store import AutoReviewReportStore
from cardforge.services.review.review_service import ReviewService


class AutoReviewService:
    """Offline-safe production review pass modeled after FilmCreator-style auto review.

    This orchestrator keeps side effects explicit: build context, score with the
    deterministic heuristic reviewer, persist durable reports, then enqueue human
    review only when the result is not a clear pass. Later LM Studio review can
    replace the scoring class without changing callers.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.prompts = PromptTemplateService(self.db)
        self.heuristics = HeuristicAutoReviewer()
        self.reports = AutoReviewReportStore(self.asset_store)

    def review_card_text(self, project_slug: str, card_key: str, *, use_mock: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            validation = self.cards.validator.validate(project_slug, card).model_dump()
            prompt_package = self.prompts.render_package(
                project_slug,
                template_key="auto_review_v1",
                task_type="card_auto_review",
                set_id=card["set_id"],
                card_id=card["id"],
                conn=conn,
                context={
                    "project_slug": project_slug,
                    "card_key": card_key,
                    "name": card["name"],
                    "card_type": card["card_type"],
                    "rules_text": card["rules_text"],
                    "validation_summary": validation,
                },
            )
            report = self.heuristics.review_card(card, validation)
            report["prompt_package_key"] = prompt_package.package_key
            report["prompt_package_path"] = prompt_package.package_markdown_path
            report = self.reports.persist_report(
                conn,
                project_id=project["id"],
                set_id=card["set_id"],
                card_id=card["id"],
                target_type="card",
                target_id=card_key,
                review_type="card_text_auto",
                report=report,
                folder=self.asset_store.project_root(project_slug) / "cards" / card_key / "auto_reviews",
            )
            if report["auto_status"] in {"needs_human_review", "needs_rework"}:
                ReviewService(self.db).enqueue(
                    project_id=project["id"],
                    set_id=card["set_id"],
                    target_type="card",
                    target_id=card_key,
                    review_type="auto_card_text",
                    title=f"Auto-review flagged card text: {card['name']}",
                    description=f"Auto status {report['auto_status']} with score {report['score_100']}.",
                    severity="high" if report["auto_status"] == "needs_rework" else "normal",
                    metadata=report,
                    conn=conn,
                )
            return report

    def review_batch_text(self, project_slug: str, batch_key: str, *, use_mock: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            batch = conn.execute(
                """
                SELECT b.* FROM card_batches b
                JOIN sets s ON s.id = b.set_id
                WHERE s.project_id = ? AND b.batch_key = ?
                """,
                (project["id"], batch_key),
            ).fetchone()
            if batch is None:
                raise KeyError(f"Batch not found: {batch_key}")
            cards = list(conn.execute("SELECT * FROM cards WHERE batch_id = ? ORDER BY card_key", (batch["id"],)))

        reports = [self.review_card_text(project_slug, card["card_key"], use_mock=use_mock) for card in cards]
        summary = {
            "batch_key": batch_key,
            "card_count": len(reports),
            "average_score_100": round(sum(item["score_100"] for item in reports) / max(1, len(reports)), 2),
            "needs_rework_count": sum(1 for item in reports if item["auto_status"] == "needs_rework"),
            "needs_human_review_count": sum(1 for item in reports if item["auto_status"] == "needs_human_review"),
            "strong_pass_count": sum(1 for item in reports if item["auto_status"] == "strong_pass"),
            "reports": reports,
        }
        path = self.asset_store.project_root(project_slug) / "batches" / batch_key / "auto_review_summary.json"
        self.asset_store.write_json(path, summary)
        return summary

    def review_art_candidate(self, project_slug: str, candidate_key: str, *, use_mock: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                """
                SELECT ac.*, c.card_key, c.name, c.set_id, c.id AS card_id
                FROM art_candidates ac
                JOIN cards c ON c.id = ac.card_id
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND ac.candidate_key = ?
                """,
                (project["id"], candidate_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Art candidate not found: {candidate_key}")
            image_path = self.asset_store.workspace_root / row["image_path"]
            report = self.heuristics.review_art_candidate(row, image_path, use_mock=use_mock)
            report = self.reports.persist_report(
                conn,
                project_id=project["id"],
                set_id=row["set_id"],
                card_id=row["card_id"],
                target_type="art_candidate",
                target_id=candidate_key,
                review_type="art_candidate_auto",
                report=report,
                folder=self.asset_store.project_root(project_slug) / "cards" / row["card_key"] / "auto_reviews",
            )
            conn.execute(
                "UPDATE art_candidates SET score_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(report, ensure_ascii=False), row["id"]),
            )
            if report["auto_status"] != "strong_pass":
                ReviewService(self.db).enqueue(
                    project_id=project["id"],
                    set_id=row["set_id"],
                    target_type="art_candidate",
                    target_id=candidate_key,
                    review_type="auto_art_candidate",
                    title=f"Auto-review flagged art candidate {candidate_key}",
                    description=f"Auto status {report['auto_status']} with score {report['score_100']}.",
                    preview_path=row["image_path"],
                    metadata=report,
                    conn=conn,
                )
            return report
