from __future__ import annotations

from typing import Any

from cardforge.db.session import Database
from cardforge.services.cards.card_service import CardService
from cardforge.services.render.card_renderer import CardRenderer


class RenderSetService:
    """Render every card in a set using the existing CardRenderer."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.cards = CardService(self.db)
        self.renderer = CardRenderer(self.db)

    def render_set(self, project_slug: str, set_code: str, *, placeholder_art: bool = True) -> dict[str, Any]:
        rows = self.cards.list_cards(project_slug, set_code)
        rendered: list[dict[str, Any]] = []
        for row in rows:
            card_key = row["card_key"]
            result = self.renderer.render_card(project_slug, card_key, placeholder_art=placeholder_art)
            rendered.append({"card_key": card_key, **result})
        return {
            "project_slug": project_slug,
            "set_code": set_code,
            "card_count": len(rows),
            "rendered_count": len(rendered),
            "rendered": rendered,
        }
