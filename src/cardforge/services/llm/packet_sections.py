from __future__ import annotations

import re

SECTION_TEXT_KEYS = {"rules_text", "flavor_text", "design_notes", "art_direction"}


def canonical_section_name(value: str) -> str:
    return {
        "rules": "rules_text",
        "rule_text": "rules_text",
        "rules_text": "rules_text",
        "effect": "rules_text",
        "flavor": "flavor_text",
        "flavor_text": "flavor_text",
        "notes": "design_notes",
        "design_note": "design_notes",
        "design_notes": "design_notes",
        "art": "art_direction",
        "illustration": "art_direction",
        "art_direction": "art_direction",
    }.get(value, value)


def plain_section_name(value: str) -> str | None:
    canonical = canonical_section_name(normalize_key(value))
    if canonical in SECTION_TEXT_KEYS:
        return canonical
    return None


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
