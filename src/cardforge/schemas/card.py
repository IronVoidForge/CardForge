from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CardCost(BaseModel):
    generic: int = 0
    resources: dict[str, int] = Field(default_factory=dict)
    display: str = ""

    @model_validator(mode="after")
    def fill_display(self) -> "CardCost":
        if not self.display:
            parts = [str(self.generic)] if self.generic else []
            parts.extend(f"{amount}{key[:1].upper()}" for key, amount in sorted(self.resources.items()) if amount)
            self.display = "".join(parts) or "0"
        return self


class CardStats(BaseModel):
    attack: int | None = None
    health: int | None = None
    armor: int | None = None


class CardRecord(BaseModel):
    card_key: str = ""
    name: str
    slug: str = ""
    card_number: str = ""
    rarity: str = "common"
    faction: str = ""
    color_identity: list[str] = Field(default_factory=list)
    card_type: str
    supertypes: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    type_line: str = ""
    cost: CardCost = Field(default_factory=CardCost)
    stats: CardStats = Field(default_factory=CardStats)
    rules_text: str = ""
    reminder_text: str = ""
    flavor_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    mechanics: list[dict[str, Any]] = Field(default_factory=list)
    design_notes: str = ""
    art_direction: str = ""
    template_id: str = ""
    back_template_id: str = "default_card_back_v1"

    @field_validator("name", "card_type")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("Field is required.")
        return value

    @model_validator(mode="after")
    def fill_type_line_and_template(self) -> "CardRecord":
        if not self.type_line:
            subtype = f" — {' '.join(self.subtypes)}" if self.subtypes else ""
            self.type_line = f"{self.card_type.title()}{subtype}"
        if not self.template_id:
            self.template_id = f"default_{self.card_type.lower()}_front_v1"
        return self


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    field: str = ""


class CardValidationReport(BaseModel):
    card_key: str
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
