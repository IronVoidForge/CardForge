from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ParsedCardDraft(BaseModel):
    name: str
    card_type: str = "creature"
    rarity: str = "common"
    faction: str = ""
    cost: int = 0
    attack: int | None = None
    health: int | None = None
    type_line: str = ""
    rules_text: str = ""
    flavor_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    design_notes: str = ""
    art_direction: str = ""
    template_id: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("Card name is required.")
        return value

    @field_validator("card_type", "rarity")
    @classmethod
    def normalize_lower(cls, value: str) -> str:
        return str(value or "").strip().lower()


class CardBatchParseResult(BaseModel):
    cards: list[ParsedCardDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
