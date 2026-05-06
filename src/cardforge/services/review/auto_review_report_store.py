from __future__ import annotations

import json
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from cardforge.files.asset_store import AssetStore


class AutoReviewReportStore:
    """Persists auto-review reports to files and SQL."""

    def __init__(self, asset_store: AssetStore) -> None:
        self.asset_store = asset_store

    def persist_report(
        self,
        conn: Connection,
        *,
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
        self.asset_store.write_text(md_path, self.report_markdown(report_with_paths))
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

    def report_markdown(self, report: dict[str, Any]) -> str:
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
