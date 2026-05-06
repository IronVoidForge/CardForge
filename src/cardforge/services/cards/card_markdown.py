from __future__ import annotations

import json
from sqlite3 import Row


def card_to_markdown(card: Row) -> str:
    cost = json.loads(card["cost_json"] or "{}")
    stats = json.loads(card["stats_json"] or "{}")
    keywords = json.loads(card["keywords_json"] or "[]")
    stat_text = ""
    if stats.get("attack") is not None or stats.get("health") is not None:
        stat_text = f"{stats.get('attack', '-')}/{stats.get('health', '-')}"
    lines = [
        f"# {card['name']}",
        "",
        f"- Card ID: {card['card_key']}",
        f"- Type: {card['type_line']}",
        f"- Rarity: {card['rarity']}",
        f"- Faction: {card['faction'] or 'None'}",
        f"- Cost: {cost.get('display', '')}",
    ]
    if stat_text:
        lines.append(f"- Stats: {stat_text}")
    if keywords:
        lines.append(f"- Keywords: {', '.join(keywords)}")
    lines.extend([
        "",
        "## Rules Text",
        "",
        card["rules_text"] or "_No rules text yet._",
        "",
        "## Flavor Text",
        "",
        f"*{card['flavor_text']}*" if card["flavor_text"] else "_No flavor text yet._",
        "",
        "## Design Notes",
        "",
        card["design_notes"] or "_No design notes yet._",
        "",
        "## Art Direction",
        "",
        card["art_direction"] or "_No art direction yet._",
        "",
    ])
    return "\n".join(lines)
