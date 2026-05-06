from __future__ import annotations

import json
from collections import Counter
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService


class BalanceReviewService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)

    def review_batch(self, project_slug: str, batch_key: str) -> dict[str, Any]:
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
            cost_curve: Counter[str] = Counter()
            type_mix: Counter[str] = Counter()
            rarity_mix: Counter[str] = Counter()
            problems: list[dict[str, Any]] = []
            for card in cards:
                cost = json.loads(card["cost_json"] or "{}")
                cost_value = int(cost.get("generic") or 0)
                bucket = "5+" if cost_value >= 5 else str(cost_value)
                cost_curve[bucket] += 1
                type_mix[str(card["card_type"])] += 1
                rarity_mix[str(card["rarity"])] += 1
                rules_len = len(str(card["rules_text"] or ""))
                stats = json.loads(card["stats_json"] or "{}")
                attack = stats.get("attack")
                health = stats.get("health")
                if cost_value <= 1 and attack is not None and health is not None and attack + health > 4:
                    problems.append({"card_key": card["card_key"], "severity": "medium", "issue": "Low-cost creature has unusually high total stats.", "suggested_fix": "Reduce attack/health or raise cost."})
                if rules_len > 360:
                    problems.append({"card_key": card["card_key"], "severity": "medium", "issue": "Rules text is long for a physical card.", "suggested_fix": "Shorten or split into one primary effect."})
                if not str(card["art_direction"] or "").strip():
                    problems.append({"card_key": card["card_key"], "severity": "low", "issue": "Missing art direction.", "suggested_fix": "Generate or write an art prompt before image generation."})
            health = "good" if not problems else ("needs_minor_tuning" if all(p["severity"] != "high" for p in problems) else "needs_major_tuning")
            summary = {
                "batch_key": batch_key,
                "overall_balance": health,
                "card_count": len(cards),
                "cost_curve": dict(sorted(cost_curve.items())),
                "type_mix": dict(type_mix),
                "rarity_mix": dict(rarity_mix),
                "problems": problems,
                "simulated_review": True,
            }
            path = self.asset_store.project_root(project_slug) / "batches" / batch_key / "balance_report.json"
            self.asset_store.write_json(path, summary)
            conn.execute(
                "UPDATE card_batches SET balance_summary_json = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(summary), "balance_reviewed", batch["id"]),
            )
            return summary
