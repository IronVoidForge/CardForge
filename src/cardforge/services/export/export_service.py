from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from sqlite3 import Row
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.sets.set_service import SetService


class ExportService:
    """Export locked/rendered set data to files without mutating source cards."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.sets = SetService(self.db)

    def export_json(self, project_slug: str, set_code: str) -> dict[str, Any]:
        return self._export_tabular(project_slug, set_code, export_type="json")

    def export_csv(self, project_slug: str, set_code: str) -> dict[str, Any]:
        return self._export_tabular(project_slug, set_code, export_type="csv")

    def export_markdown_catalog(self, project_slug: str, set_code: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            cards = self._cards_for_set(conn, set_row["id"])
            export_dir = self.asset_store.project_root(project_slug) / "exports" / "markdown"
            export_dir.mkdir(parents=True, exist_ok=True)
            out = export_dir / f"{set_code.lower()}_catalog.md"
            sections = [f"# {set_row['name']} Card Catalog", ""]
            for card in cards:
                cost = json.loads(card["cost_json"] or "{}")
                stats = json.loads(card["stats_json"] or "{}")
                sections.extend(
                    [
                        f"## {card['name']}",
                        "",
                        f"- ID: {card['card_key']}",
                        f"- Type: {card['type_line'] or card['card_type']}",
                        f"- Rarity: {card['rarity']}",
                        f"- Cost: {cost.get('display', cost.get('generic', 0))}",
                        f"- Stats: {stats.get('attack', '-')}/{stats.get('health', '-')}" if stats else "- Stats: —",
                        "",
                        card["rules_text"] or "_No rules text._",
                        "",
                    ]
                )
            out.write_text("\n".join(sections), encoding="utf-8")
            record = self._record_export(conn, set_row["id"], "markdown", out)
            return {"export_type": "markdown", "output_path": self.asset_store.relative_to_workspace(out), "card_count": len(cards), "export_id": record["id"]}

    def export_png_bundle(self, project_slug: str, set_code: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            rows = conn.execute(
                """
                SELECT c.card_key, c.name, r.front_path, r.back_path, r.preview_path
                FROM cards c
                LEFT JOIN renders r ON r.id = (
                    SELECT id FROM renders rr WHERE rr.card_id = c.id ORDER BY rr.created_at DESC, rr.id DESC LIMIT 1
                )
                WHERE c.set_id = ?
                ORDER BY c.card_key
                """,
                (set_row["id"],),
            ).fetchall()
            export_dir = self.asset_store.project_root(project_slug) / "exports" / "png" / set_code.lower()
            fronts_dir = export_dir / "fronts"
            backs_dir = export_dir / "backs"
            previews_dir = export_dir / "previews"
            for folder in (fronts_dir, backs_dir, previews_dir):
                folder.mkdir(parents=True, exist_ok=True)
            copied = 0
            missing: list[str] = []
            for row in rows:
                if not row["front_path"] or not row["back_path"]:
                    missing.append(row["card_key"])
                    continue
                front = self.asset_store.safe_resolve(row["front_path"])
                back = self.asset_store.safe_resolve(row["back_path"])
                preview = self.asset_store.safe_resolve(row["preview_path"]) if row["preview_path"] else None
                if not front.exists() or not back.exists():
                    missing.append(row["card_key"])
                    continue
                shutil.copy2(front, fronts_dir / f"{row['card_key']}_{self._safe_name(row['name'])}_front.png")
                shutil.copy2(back, backs_dir / f"{row['card_key']}_{self._safe_name(row['name'])}_back.png")
                if preview and preview.exists():
                    shutil.copy2(preview, previews_dir / f"{row['card_key']}_{self._safe_name(row['name'])}_preview.png")
                copied += 1
            manifest_path = export_dir / "EXPORT_MANIFEST.json"
            manifest = {"set_code": set_code, "copied_card_count": copied, "missing_render_cards": missing}
            self.asset_store.write_json(manifest_path, manifest)
            record = self._record_export(conn, set_row["id"], "png", export_dir, settings={"missing_render_cards": missing})
            return {
                "export_type": "png",
                "output_path": self.asset_store.relative_to_workspace(export_dir),
                "copied_card_count": copied,
                "missing_render_cards": missing,
                "export_id": record["id"],
            }

    def _export_tabular(self, project_slug: str, set_code: str, *, export_type: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            cards = self._cards_for_set(conn, set_row["id"])
            payload = [self._card_export_payload(card) for card in cards]
            export_dir = self.asset_store.project_root(project_slug) / "exports" / export_type
            export_dir.mkdir(parents=True, exist_ok=True)
            if export_type == "json":
                out = export_dir / f"{set_code.lower()}_cards.json"
                out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif export_type == "csv":
                out = export_dir / f"{set_code.lower()}_cards.csv"
                with out.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(payload[0].keys()) if payload else ["card_key", "name"])
                    writer.writeheader()
                    writer.writerows(payload)
            else:
                raise ValueError(f"Unsupported tabular export: {export_type}")
            record = self._record_export(conn, set_row["id"], export_type, out)
            return {"export_type": export_type, "output_path": self.asset_store.relative_to_workspace(out), "card_count": len(cards), "export_id": record["id"]}

    def _cards_for_set(self, conn: Any, set_id: int) -> list[Row]:
        return list(conn.execute("SELECT * FROM cards WHERE set_id = ? ORDER BY card_key", (set_id,)))

    def _card_export_payload(self, card: Row) -> dict[str, Any]:
        cost = json.loads(card["cost_json"] or "{}")
        stats = json.loads(card["stats_json"] or "{}")
        return {
            "card_key": card["card_key"],
            "name": card["name"],
            "card_type": card["card_type"],
            "type_line": card["type_line"],
            "rarity": card["rarity"],
            "faction": card["faction"],
            "cost": cost.get("display", cost.get("generic", 0)),
            "attack": stats.get("attack"),
            "health": stats.get("health"),
            "rules_text": card["rules_text"],
            "flavor_text": card["flavor_text"],
            "art_direction": card["art_direction"],
            "status": card["status"],
        }

    def _record_export(self, conn: Any, set_id: int, export_type: str, output_path: Path, *, settings: dict[str, Any] | None = None) -> Row:
        conn.execute(
            """
            INSERT INTO exports(set_id, export_type, status, settings_json, output_path, completed_at)
            VALUES(?, ?, 'completed', ?, ?, CURRENT_TIMESTAMP)
            """,
            (set_id, export_type, json.dumps(settings or {}), self.asset_store.relative_to_workspace(output_path)),
        )
        return conn.execute("SELECT * FROM exports WHERE id = last_insert_rowid()").fetchone()

    def _safe_name(self, name: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned[:48] or "card"
