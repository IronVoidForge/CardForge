from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cardforge.cli.main import app
from cardforge.services.batches.card_payload_parser import payload_to_card_record, record_to_card_payload
from cardforge.services.llm.packet_parser import PacketRecord


runner = CliRunner()


def test_cli_is_composed_from_subcommand_modules() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command_name in ["project", "set", "card", "batch", "art", "review", "prompt", "auto"]:
        assert command_name in result.output


def test_card_payload_parser_is_independent_of_batch_service() -> None:
    packet_record = PacketRecord(
        fields={"type": "card", "name": "Crypt Bell", "card_type": "spell", "cost": "2", "rarity": "common"},
        sections={"rules_text": "Draw a card, then discard a card.", "art_direction": "A rusted bell in a crypt."},
    )
    payload = record_to_card_payload(packet_record)
    card = payload_to_card_record(payload)
    assert card.name == "Crypt Bell"
    assert card.card_type == "spell"
    assert card.cost.generic == 2
    assert card.rules_text.startswith("Draw")


def test_large_implementation_files_were_split() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "src" / "cardforge" / "cli" / "commands" / "cards.py").exists()
    assert (root / "src" / "cardforge" / "services" / "cards" / "card_file_writer.py").exists()
    assert (root / "src" / "cardforge" / "services" / "review" / "auto_review_heuristics.py").exists()
