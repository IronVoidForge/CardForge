from __future__ import annotations

from dataclasses import dataclass

CARD_TYPE_SEQUENCE = ["creature", "creature", "spell", "equipment", "location", "creature", "spell", "legendary", "creature", "spell", "equipment", "location", "creature", "spell", "creature"]
RARITY_SEQUENCE = ["common", "common", "common", "uncommon", "uncommon", "common", "uncommon", "rare", "common", "common", "uncommon", "rare", "common", "uncommon", "rare"]


@dataclass(frozen=True)
class MockCardSeed:
    name: str
    card_type: str
    rarity: str
    cost: int
    attack: int | None
    health: int | None
    keywords: list[str]
    rules_text: str
    flavor_text: str
    design_notes: str
    art_direction: str


NAMES = [
    "Bone Lantern Warden",
    "Grave-Candle Acolyte",
    "Ossuary Gale",
    "Mourner's Hookblade",
    "Chapel of Last Whispers",
    "Cryptmire Reclaimer",
    "Violet Funeral Rite",
    "The Hollow Abbot",
    "Marrow-Sewn Sentinel",
    "Ashes to Oath",
    "Bell of the Buried",
    "Moonlit Mausoleum",
    "Wisp-Herd Undertaker",
    "Debt of the Dead",
    "Sepulcher Crown-Bearer",
]


def build_mock_card_batch_packet(*, batch_key: str, request_text: str, count: int) -> str:
    """Build a deterministic CardForge packet so tests/manual smoke do not require LM Studio."""

    seeds = [_seed_for_index(index, request_text) for index in range(max(1, count))]
    lines = [
        "[[CARDFORGE_PACKET]]",
        "task: card_batch",
        "version: 1",
        f"batch_id: {batch_key}",
        "source: mock_cardforge_llm",
        "",
    ]
    for index, seed in enumerate(seeds, start=1):
        stats_lines = []
        if seed.attack is not None:
            stats_lines.append(f"attack: {seed.attack}")
        if seed.health is not None:
            stats_lines.append(f"health: {seed.health}")
        lines.extend(
            [
                "[[CARDFORGE_RECORD]]",
                "type: card",
                f"name: {seed.name}",
                f"card_type: {seed.card_type}",
                f"rarity: {seed.rarity}",
                "faction: Gravebound",
                f"cost: {seed.cost}",
                f"keywords: {', '.join(seed.keywords)}",
                *stats_lines,
                "template_id: default_" + seed.card_type + "_front_v1",
                "back_template_id: default_card_back_v1",
                "",
                "[[SECTION rules_text]]",
                seed.rules_text,
                "[[/SECTION]]",
                "",
                "[[SECTION flavor_text]]",
                seed.flavor_text,
                "[[/SECTION]]",
                "",
                "[[SECTION design_notes]]",
                seed.design_notes,
                "[[/SECTION]]",
                "",
                "[[SECTION art_direction]]",
                seed.art_direction,
                "[[/SECTION]]",
                "[[/CARDFORGE_RECORD]]",
                "",
            ]
        )
    lines.append("[[/CARDFORGE_PACKET]]")
    return "\n".join(lines) + "\n"


def _seed_for_index(index: int, request_text: str) -> MockCardSeed:
    card_type = CARD_TYPE_SEQUENCE[index % len(CARD_TYPE_SEQUENCE)]
    rarity = RARITY_SEQUENCE[index % len(RARITY_SEQUENCE)]
    name = NAMES[index % len(NAMES)]
    mood = "gothic" if "goth" in request_text.lower() or "necro" in request_text.lower() else "mythic"
    cost = 1 + (index % 5)
    keywords_by_type = {
        "creature": ["guard"] if index % 2 == 0 else ["sacrifice"],
        "spell": ["curse"] if index % 2 == 0 else ["graveyard"],
        "equipment": ["sacrifice"],
        "location": ["graveyard"],
        "legendary": ["summon", "graveyard"],
    }
    if card_type in {"creature", "legendary"}:
        attack = max(1, cost - 1)
        health = cost + (2 if card_type == "legendary" else 1)
        rules = (
            "Guard.\n"
            "Whenever another friendly card is sacrificed, this gains +1 health until end of turn."
            if card_type == "creature"
            else "When this enters play, summon two 1/1 Bone Wisps.\nWhenever a friendly token dies, drain 1 life."
        )
    elif card_type == "spell":
        attack = health = None
        rules = "Choose one: curse an enemy, or return a low-cost creature from your graveyard to your hand."
    elif card_type == "equipment":
        attack = health = None
        rules = "Equipped creature gets +1 attack. When it dies, create a 1/1 Bone Wisp."
    else:
        attack = health = None
        rules = "At the start of your turn, you may sacrifice a token. If you do, draw a card then discard a card."
    return MockCardSeed(
        name=name,
        card_type=card_type,
        rarity=rarity,
        cost=cost,
        attack=attack,
        health=health,
        keywords=keywords_by_type.get(card_type, []),
        rules_text=rules,
        flavor_text="Every grave has a door, and every door has a keeper.",
        design_notes=f"Mock-generated {card_type} for a {mood} prototype set. Intended for low-risk local testing.",
        art_direction=(
            f"{mood} fantasy card illustration of {name.lower()}, bone-white highlights, deep violet shadows, "
            "clear central silhouette, no text, no border, no logo."
        ),
    )
