from __future__ import annotations

import json
import re
from typing import Any

from cardforge.schemas.card import CardCost, CardRecord, CardStats
from cardforge.services.llm.packet_parser import PacketRecord


def record_to_card_payload(record: PacketRecord) -> dict[str, Any]:
    fields = {key.lower(): value for key, value in record.fields.items()}
    sections = {key.lower(): value for key, value in record.sections.items()}
    payload = dict(fields)
    for section in ("rules_text", "flavor_text", "design_notes", "art_direction"):
        if section in sections:
            payload[section] = sections[section]
    return payload


def payload_to_card_record(payload: dict[str, Any]) -> CardRecord:
    card_type = normalize_card_type(payload.get("card_type") or payload.get("type_line") or "creature")
    return CardRecord(
        name=str(payload.get("name") or "Unnamed Card").strip(),
        card_type=card_type,
        rarity=str(payload.get("rarity") or "common").strip().lower(),
        faction=str(payload.get("faction") or "").strip(),
        type_line=str(payload.get("type_line") or "").strip(),
        cost=coerce_cost(payload.get("cost")),
        stats=CardStats(attack=coerce_int(payload.get("attack")), health=coerce_int(payload.get("health"))),
        rules_text=str(payload.get("rules_text") or "").strip(),
        flavor_text=str(payload.get("flavor_text") or "").strip(),
        keywords=coerce_string_list(payload.get("keywords")),
        mechanics=coerce_json_list(payload.get("mechanics")),
        subtypes=coerce_string_list(payload.get("subtypes")),
        design_notes=str(payload.get("design_notes") or "").strip(),
        art_direction=str(payload.get("art_direction") or "").strip(),
        template_id=str(payload.get("template_id") or "").strip(),
        back_template_id=str(payload.get("back_template_id") or "default_card_back_v1").strip(),
    )


def normalize_card_type(value: Any) -> str:
    card_type = str(value or "creature").strip().lower()
    return "creature" if card_type.startswith("creature") else card_type


def coerce_cost(value: Any) -> CardCost:
    if isinstance(value, CardCost):
        return value
    if isinstance(value, dict):
        return CardCost(**value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            try:
                return CardCost(**json.loads(text))
            except json.JSONDecodeError:
                pass
        match = re.search(r"\d+", text)
        return CardCost(generic=int(match.group(0)) if match else 0, display=text or "0")
    if isinstance(value, int):
        return CardCost(generic=value)
    return CardCost()


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                return [str(item).strip().lower() for item in payload if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [part.strip().lower().replace(" ", "_") for part in re.split(r"[,;\n]+", text) if part.strip()]


def coerce_json_list(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            payload = json.loads(value)
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
        except json.JSONDecodeError:
            return []
    return []
