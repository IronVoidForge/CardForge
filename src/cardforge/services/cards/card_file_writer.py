from __future__ import annotations

import json
from sqlite3 import Row

from cardforge.files.asset_store import AssetStore
from cardforge.services.cards.card_markdown import card_to_markdown

CARD_JSON_FIELDS = ("cost_json", "stats_json", "keywords_json", "mechanics_json")
LIST_JSON_FIELDS = {"keywords_json", "mechanics_json"}


class CardFileWriter:
    """Owns card-facing artifact writes so CardService can stay focused on state changes."""

    def __init__(self, asset_store: AssetStore) -> None:
        self.asset_store = asset_store

    def write_card_files(self, project_slug: str, card: Row) -> None:
        root = self.asset_store.project_root(project_slug) / "cards" / card["card_key"]
        payload = self._payload_from_row(card)
        self.asset_store.write_json(root / "card.json", payload)
        self.asset_store.write_text(root / "card.md", card_to_markdown(card))

    def _payload_from_row(self, card: Row) -> dict[str, object]:
        payload: dict[str, object] = {key: card[key] for key in card.keys()}
        for json_field in CARD_JSON_FIELDS:
            target_key = json_field.removesuffix("_json")
            default = "[]" if json_field in LIST_JSON_FIELDS else "{}"
            payload[target_key] = json.loads(card[json_field] or default)
        return payload
