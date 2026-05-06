from __future__ import annotations

import itertools

CARD_NAMES = [
    "Grave-Candle Acolyte",
    "Bone Lantern Warden",
    "Carrion Choir",
    "Ashen Pact",
    "Crypt Map",
    "Mourning Blade",
    "Sepulcher Gate",
    "Black Bell Procession",
    "Hollow Crown Regent",
    "Wisp-Tether Hex",
    "Ossuary Quartermaster",
    "Violet Funeral Pyre",
    "Gravebound Banner",
    "Moonlit Catacomb",
    "Last Rite Colossus",
]

TYPE_CYCLE = ["creature", "creature", "spell", "equipment", "location", "legendary"]


class OfflineCardLLMSimulator:
    """Deterministic stand-in for LM Studio during tests and offline development."""

    def card_batch_packet(self, *, count: int, request_text: str = "", batch_key: str = "BATCH_0001") -> str:
        records: list[str] = []
        for index, (name, card_type) in enumerate(itertools.islice(zip(itertools.cycle(CARD_NAMES), itertools.cycle(TYPE_CYCLE)), count), start=1):
            rarity = "common" if index <= max(1, count // 2) else ("uncommon" if index < count else "rare")
            cost = 1 + (index % 5)
            attack = "" if card_type in {"spell", "equipment", "location"} else str(max(1, cost - 1))
            health = "" if card_type in {"spell", "equipment", "location"} else str(cost + 1)
            rules = self._rules_for(card_type, index)
            art = self._art_for(name, card_type)
            records.append(
                f"""[[CARDFORGE_RECORD]]
type: card
name: {name}
card_type: {card_type}
rarity: {rarity}
faction: Gravebound
cost: {cost}
attack: {attack}
health: {health}
keywords: graveyard, sacrifice
template_id: default_{card_type}_front_v1

[[SECTION rules_text]]
{rules}
[[/SECTION]]

[[SECTION flavor_text]]
The dead remember every debt.
[[/SECTION]]

[[SECTION design_notes]]
Offline simulated card generated from request: {request_text[:120]}
[[/SECTION]]

[[SECTION art_direction]]
{art}
[[/SECTION]]
[[/CARDFORGE_RECORD]]"""
            )
        return "\n\n".join(
            [
                "[[CARDFORGE_PACKET]]",
                "task: card_batch",
                "version: 1",
                f"batch_id: {batch_key}",
                "",
                *records,
                "[[/CARDFORGE_PACKET]]",
            ]
        )

    def repaired_rules_text(self, *, name: str, original_rules: str, reason: str) -> str:
        base = " ".join(str(original_rules or "").replace("\n", " ").split())
        if len(base) > 180:
            base = base[:177].rstrip() + "..."
        if not base:
            base = f"When you play {name}, gain 1 advantage."
        return f"{base}\nReworked: {reason or 'clarified for play.'}"

    def _rules_for(self, card_type: str, index: int) -> str:
        if card_type == "creature":
            return "Guard. When another friendly unit dies, this gains +1 health until end of turn."
        if card_type == "spell":
            return "Return a unit from your discard pile to your hand. If a unit died this turn, draw a card."
        if card_type == "equipment":
            return "Equipped unit gets +1 attack. When it dies, create a 1/1 Bone Wisp."
        if card_type == "location":
            return "At the start of your turn, mill one card. Once each turn, you may sacrifice a unit to gain 1 resource."
        return "Legendary. Whenever a friendly unit dies, create a Bone Wisp. At end of turn, drain each opponent for 1."

    def _art_for(self, name: str, card_type: str) -> str:
        return (
            f"Dark fantasy trading card illustration of {name}, {card_type} theme, gothic necromancer faction, "
            "bone-white highlights, violet grave mist, readable silhouette, no text, no border, no logo."
        )
