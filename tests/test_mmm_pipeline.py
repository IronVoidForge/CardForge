from __future__ import annotations

import json

from cardforge.db.session import Database
from cardforge.services.export.print_sheet_service import PrintSheetExportService
from cardforge.services.importers.mmm_import_service import MMMImportService
from cardforge.services.render.set_renderer import RenderSetService


def test_mmm_import_render_and_print_sheet_pipeline(db: Database, workspace) -> None:
    player_deck = workspace / "player.json"
    monsters = workspace / "monsters.json"
    player_deck.write_text(
        json.dumps(
            [
                {
                    "id": "PLY-G1-001",
                    "title": "Rune Addition",
                    "front_text": {"problem": "2 + 3", "solve_path": "Add the runes."},
                    "guide_data": {"answer": "5"},
                    "art": {"prompt": "A glowing math rune."},
                }
            ]
        ),
        encoding="utf-8",
    )
    monsters.write_text(
        json.dumps(
            {
                "monster_cards": [
                    {
                        "id": "MON-G1-001",
                        "name": "Counting Wisp",
                        "hp": {"base": 6},
                        "attack": {"name": "Number Nudge", "damage": 2},
                        "special_ability": {"name": "Borrow", "rules_text": "Ask for one hint."},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    imported = MMMImportService(db).import_mmm(
        "magic_math_monsters",
        player_deck_path=player_deck,
        monsters_path=monsters,
    )
    assert imported["created_card_count"] == 2

    rendered = RenderSetService(db).render_set("magic_math_monsters", "PLAYER", placeholder_art=True)
    assert rendered["rendered_count"] == 1

    sheets = PrintSheetExportService(db).export_print_sheets("magic_math_monsters", "PLAYER")
    assert sheets["missing_render_cards"] == []
    assert len(sheets["sheet_paths"]) == 1
    assert (workspace / sheets["sheet_paths"][0]).exists()
