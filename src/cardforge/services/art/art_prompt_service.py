from __future__ import annotations

import json
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_service import CardService


class ArtPromptService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)

    def create_prompt(self, project_slug: str, card_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            version_row = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS n FROM art_prompts WHERE card_id = ?",
                (card["id"],),
            ).fetchone()
            version = int(version_row["n"] or 0) + 1
            positive = self._positive_prompt(card)
            negative = "text, watermark, logo, card border, frame, UI, unreadable letters, low quality, extra limbs"
            prompt_json = {
                "card_key": card_key,
                "name": card["name"],
                "card_type": card["card_type"],
                "positive_prompt": positive,
                "negative_prompt": negative,
                "target_aspect_ratio": "4:3",
                "offline_safe": True,
            }
            prompt_dir = self.asset_store.project_root(project_slug) / "cards" / card_key / "prompts"
            prompt_path = prompt_dir / f"art_prompt_v{version:03d}.md"
            self.asset_store.write_text(
                prompt_path,
                "\n".join([
                    f"# Art Prompt {card_key} v{version:03d}",
                    "",
                    "## Positive Prompt",
                    positive,
                    "",
                    "## Negative Prompt",
                    negative,
                    "",
                ]) + "\n",
            )
            conn.execute(
                """
                INSERT INTO art_prompts(card_id, version_number, positive_prompt, negative_prompt, prompt_json, prompt_markdown_path, status)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (card["id"], version, positive, negative, json.dumps(prompt_json), self.asset_store.relative_to_workspace(prompt_path), "ready"),
            )
            prompt_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
            return {"art_prompt_id": prompt_id, "card_key": card_key, "version": version, "positive_prompt": positive, "negative_prompt": negative, "prompt_markdown_path": self.asset_store.relative_to_workspace(prompt_path)}

    def latest_prompt(self, project_slug: str, card_key: str):
        with self.db.connection() as conn:
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            return conn.execute("SELECT * FROM art_prompts WHERE card_id = ? ORDER BY version_number DESC LIMIT 1", (card["id"],)).fetchone()

    def _positive_prompt(self, card) -> str:
        art_direction = str(card["art_direction"] or "").strip()
        base = art_direction or f"Fantasy card illustration of {card['name']}, {card['card_type']} card, readable silhouette"
        return f"{base}, painterly fantasy trading card art, dramatic lighting, centered composition, no text, no card frame"
