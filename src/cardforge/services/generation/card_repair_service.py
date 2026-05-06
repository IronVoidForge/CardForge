from __future__ import annotations

import re
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus
from cardforge.services.cards.card_service import CardService


class CardRepairService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.cards = CardService(self.db)

    def repair_rules_text_offline(self, project_slug: str, card_key: str, *, reason: str = "offline text fit repair") -> dict[str, Any]:
        card = self.cards.get_card(project_slug, card_key)
        original = str(card["rules_text"] or "")
        repaired = self._shorten_rules_text(original)
        updated = self.cards.update_card_fields(
            project_slug,
            card_key,
            rules_text=repaired,
            status=CardStatus.NEEDS_REPAIR.value,
            source="offline_rules_repair",
            change_reason=reason,
        )
        return {"card_key": card_key, "changed": repaired != original, "old_rules_text": original, "new_rules_text": updated["rules_text"]}

    def _shorten_rules_text(self, text: str, *, max_chars: int = 260) -> str:
        collapsed = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(collapsed) <= max_chars:
            return collapsed
        sentences = re.split(r"(?<=[.!?])\s+", collapsed)
        out: list[str] = []
        for sentence in sentences:
            if len(" ".join([*out, sentence]).strip()) > max_chars:
                break
            out.append(sentence)
        if out:
            return " ".join(out).strip()
        return collapsed[: max_chars - 1].rstrip(" ,;:") + "."
