from __future__ import annotations

from cardforge.services.llm.packet_parser import parse_card_records_flexible, parse_packet_document


def test_packet_parser_handles_fenced_packet_and_sections() -> None:
    text = """```text
[[CARDFORGE_PACKET]]
task: card_batch
version: 1

[[CARDFORGE_RECORD]]
type: card
name: Grave-Candle Acolyte
card_type: creature
cost: 2
attack: 1
health: 3
[[SECTION rules_text]]
When this enters play, create a Bone Wisp.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]
```"""
    document = parse_packet_document(text, expected_task="card_batch")
    assert len(document.records) == 1
    assert document.records[0].fields["name"] == "Grave-Candle Acolyte"
    assert "Bone Wisp" in document.records[0].sections["rules_text"]


def test_parser_salvages_markdown_table_cards() -> None:
    text = """
| Name | Type | Cost | Attack | Health | Rules | Art |
| --- | --- | --- | --- | --- | --- | --- |
| Bone Lantern Warden | creature | 3 | 2 | 4 | Guard.<br>Draw on death. | Skeletal guard, violet lantern. |
"""
    records = parse_card_records_flexible(text)
    assert records[0].fields["name"] == "Bone Lantern Warden"
    assert records[0].fields["card_type"] == "creature"
    assert "Draw" in records[0].sections["rules_text"]


def test_parser_salvages_heading_block_cards() -> None:
    text = """
## Crypt Map
- Type: equipment
- Cost: 2
- Rarity: uncommon

Rules Text
Find a location card, then discard a card.

Art Direction
An ancient map inked on bone parchment.
"""
    records = parse_card_records_flexible(text)
    assert records[0].fields["name"] == "Crypt Map"
    assert records[0].fields["card_type"] == "equipment"
    assert "location" in records[0].sections["rules_text"]
