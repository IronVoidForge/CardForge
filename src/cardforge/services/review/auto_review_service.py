from __future__ import annotations

import json
import re
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.rules_review_service import AMBIGUOUS_PATTERNS
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.review.review_service import ReviewService


class AutoReviewService:
    """Offline-safe production review pass modeled after FilmCreator-style auto review.

    The service writes durable reports, stores a DB row, and opens human review
    items when a card/candidate is not clearly ready. Later the heuristic body
    can be swapped for an LM Studio call without changing callers.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.prompts = PromptTemplateService(self.db)

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
            report = self._heuristic_card_report(card, validation)
            report["prompt_package_key"] = prompt_package.package_key
            report["prompt_package_path"] = prompt_package.package_markdown_path
            report = self._persist_report(
                conn,
                project_slug=project_slug,
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
            findings: list[dict[str, str]] = []
            recommendations: list[str] = []
            score = 100
            if not image_path.exists():
                score -= 65
                findings.append({"code": "missing_image", "severity": "error", "message": "Candidate image file is missing."})
                recommendations.append("Regenerate the art candidate.")
            if row["status"] == "rejected":
                score -= 40
                findings.append({"code": "already_rejected", "severity": "warning", "message": "Candidate was already rejected."})
            if row["status"] == "locked":
                findings.append({"code": "locked_art", "severity": "info", "message": "Candidate is locked as canonical art."})
            if "dummy" in str(row["workflow_key"] or ""):
                score -= 5
                findings.append({"code": "dummy_candidate", "severity": "info", "message": "Offline dummy art candidate; replace with ComfyUI art before final print."})
            auto_status = "strong_pass" if score >= 85 else ("needs_human_review" if score >= 65 else "needs_rework")
            report = {
                "target_type": "art_candidate",
                "target_id": candidate_key,
                "card_key": row["card_key"],
                "auto_status": auto_status,
                "score_100": max(0, min(100, score)),
                "findings": findings,
                "recommendations": recommendations,
                "simulated_review": use_mock,
            }
            report = self._persist_report(
                conn,
                project_slug=project_slug,
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

    def _heuristic_card_report(self, card: Any, validation: dict[str, Any]) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        recommendations: list[str] = []
        score = 100
        for issue in validation.get("issues", []):
            severity = issue.get("severity", "warning")
            score -= 35 if severity == "error" else 10
            findings.append({"code": issue.get("code", "validation_issue"), "severity": severity, "message": issue.get("message", "")})
            if issue.get("code") in {"missing_rules_text", "missing_type_line", "missing_template"}:
                recommendations.append("Run card autofill to complete missing required fields.")
            if issue.get("code") == "rules_text_too_long":
                recommendations.append("Run card refinement to shorten rules text for the template.")
        rules_text = str(card["rules_text"] or "")
        if rules_text and not rules_text.rstrip().endswith((".", "!", ")")):
            score -= 8
            findings.append({"code": "punctuation", "severity": "warning", "message": "Rules text should end with clean punctuation."})
            recommendations.append("Refine rules text punctuation.")
        for pattern, message in AMBIGUOUS_PATTERNS:
            if pattern.search(rules_text):
                score -= 10
                findings.append({"code": "ambiguous_rules", "severity": "warning", "message": message})
                recommendations.append("Clarify ambiguous rules wording.")
        if not str(card["art_direction"] or "").strip():
            score -= 12
            findings.append({"code": "missing_art_direction", "severity": "warning", "message": "Art direction is missing."})
            recommendations.append("Autofill art direction before generating art.")
        if len(rules_text) > 420:
            score -= 15
            findings.append({"code": "text_fit_risk", "severity": "warning", "message": "Rules text may overflow the template."})
            recommendations.append("Shorten the rules text.")
        score = max(0, min(100, score))
        auto_status = "strong_pass" if score >= 85 and validation.get("valid") else ("needs_human_review" if score >= 65 and validation.get("valid") else "needs_rework")
        return {
            "target_type": "card",
            "target_id": card["card_key"],
            "card_key": card["card_key"],
            "auto_status": auto_status,
            "score_100": score,
            "findings": findings,
            "recommendations": sorted(set(recommendations)),
            "validation": validation,
            "simulated_review": True,
        }

    def _persist_report(
        self,
        conn: Connection,
        *,
        project_slug: str,
        project_id: int,
        set_id: int | None,
        card_id: int | None,
        target_type: str,
        target_id: str,
        review_type: str,
        report: dict[str, Any],
        folder: Path,
    ) -> dict[str, Any]:
        folder.mkdir(parents=True, exist_ok=True)
        next_index = len(list(folder.glob(f"{target_type}_{target_id}_*.json"))) + 1
        json_path = folder / f"{target_type}_{target_id}_auto_review_v{next_index:03d}.json"
        md_path = folder / f"{target_type}_{target_id}_auto_review_v{next_index:03d}.md"
        report_with_paths = dict(report)
        report_with_paths["report_json_path"] = self.asset_store.relative_to_workspace(json_path)
        report_with_paths["report_markdown_path"] = self.asset_store.relative_to_workspace(md_path)
        self.asset_store.write_json(json_path, report_with_paths)
        self.asset_store.write_text(md_path, self._report_markdown(report_with_paths))
        conn.execute(
            """
            INSERT INTO auto_reviews(
                project_id, set_id, card_id, target_type, target_id, review_type, auto_status, score_100,
                findings_json, recommendations_json, report_json_path, report_markdown_path, source_model, status
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (
                project_id,
                set_id,
                card_id,
                target_type,
                target_id,
                review_type,
                report_with_paths["auto_status"],
                int(report_with_paths["score_100"]),
                json.dumps(report_with_paths.get("findings", []), ensure_ascii=False),
                json.dumps(report_with_paths.get("recommendations", []), ensure_ascii=False),
                report_with_paths["report_json_path"],
                report_with_paths["report_markdown_path"],
                "offline_heuristic",
            ),
        )
        return report_with_paths

    def _report_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            f"# Auto Review: {report.get('target_id', '')}",
            "",
            f"- Target Type: {report.get('target_type', '')}",
            f"- Status: {report.get('auto_status', '')}",
            f"- Score: {report.get('score_100', 0)}/100",
            "",
            "## Findings",
        ]
        findings = report.get("findings", []) or []
        if findings:
            for item in findings:
                lines.append(f"- {item.get('severity', 'info')}: {item.get('code', '')} — {item.get('message', '')}")
        else:
            lines.append("- No blocking findings.")
        lines.extend(["", "## Recommendations"])
        recs = report.get("recommendations", []) or []
        if recs:
            for item in recs:
                lines.append(f"- {item}")
        else:
            lines.append("- No automated rework recommended.")
        return "\n".join(lines) + "\n"
