from __future__ import annotations

from pathlib import Path
from sqlite3 import Row
from typing import Any

from cardforge.services.generation.rules_review_service import AMBIGUOUS_PATTERNS


class HeuristicAutoReviewer:
    """Offline-safe scoring rules for cards and art candidates.

    The class is intentionally deterministic so tests do not need LM Studio or
    ComfyUI. A later LLM reviewer can be added behind the same report shape.
    """

    def review_card(self, card: Row, validation: dict[str, Any]) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        recommendations: list[str] = []
        score = 100
        for issue in validation.get("issues", []):
            severity = issue.get("severity", "warning")
            score -= 35 if severity == "error" else 10
            findings.append(
                {
                    "code": issue.get("code", "validation_issue"),
                    "severity": severity,
                    "message": issue.get("message", ""),
                }
            )
            if issue.get("code") in {"missing_rules_text", "missing_type_line", "missing_template"}:
                recommendations.append("Run card autofill to complete missing required fields.")
            if issue.get("code") == "rules_text_too_long":
                recommendations.append("Run card refinement to shorten rules text for the template.")

        rules_text = str(card["rules_text"] or "")
        if rules_text and not rules_text.rstrip().endswith((".", "!", ")")):
            score -= 8
            findings.append(
                {
                    "code": "punctuation",
                    "severity": "warning",
                    "message": "Rules text should end with clean punctuation.",
                }
            )
            recommendations.append("Refine rules text punctuation.")
        for pattern, message in AMBIGUOUS_PATTERNS:
            if pattern.search(rules_text):
                score -= 10
                findings.append({"code": "ambiguous_rules", "severity": "warning", "message": message})
                recommendations.append("Clarify ambiguous rules wording.")
        if not str(card["art_direction"] or "").strip():
            score -= 12
            findings.append(
                {"code": "missing_art_direction", "severity": "warning", "message": "Art direction is missing."}
            )
            recommendations.append("Autofill art direction before generating art.")
        if len(rules_text) > 420:
            score -= 15
            findings.append(
                {
                    "code": "text_fit_risk",
                    "severity": "warning",
                    "message": "Rules text may overflow the template.",
                }
            )
            recommendations.append("Shorten the rules text.")

        score = max(0, min(100, score))
        auto_status = self._card_status(score=score, validation=validation)
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

    def review_art_candidate(self, row: Row, image_path: Path, *, use_mock: bool = True) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        recommendations: list[str] = []
        score = 100
        if not image_path.exists():
            score -= 65
            findings.append(
                {"code": "missing_image", "severity": "error", "message": "Candidate image file is missing."}
            )
            recommendations.append("Regenerate the art candidate.")
        if row["status"] == "rejected":
            score -= 40
            findings.append(
                {"code": "already_rejected", "severity": "warning", "message": "Candidate was already rejected."}
            )
        if row["status"] == "locked":
            findings.append({"code": "locked_art", "severity": "info", "message": "Candidate is locked as canonical art."})
        if "dummy" in str(row["workflow_key"] or ""):
            score -= 5
            findings.append(
                {
                    "code": "dummy_candidate",
                    "severity": "info",
                    "message": "Offline dummy art candidate; replace with ComfyUI art before final print.",
                }
            )
        score = max(0, min(100, score))
        auto_status = "strong_pass" if score >= 85 else ("needs_human_review" if score >= 65 else "needs_rework")
        return {
            "target_type": "art_candidate",
            "target_id": row["candidate_key"],
            "card_key": row["card_key"],
            "auto_status": auto_status,
            "score_100": score,
            "findings": findings,
            "recommendations": recommendations,
            "simulated_review": use_mock,
        }

    def _card_status(self, *, score: int, validation: dict[str, Any]) -> str:
        if score >= 85 and validation.get("valid"):
            return "strong_pass"
        if score >= 65 and validation.get("valid"):
            return "needs_human_review"
        return "needs_rework"
