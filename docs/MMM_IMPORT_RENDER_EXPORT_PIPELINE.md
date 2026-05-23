# Magic, Math, & Monsters import/render/export pipeline

This branch adds native Magic, Math, & Monsters support to CardForge.

## Goals

- Import MMM Player Deck JSON into a PLAYER set.
- Import MMM Loot Insert JSON into the PLAYER set.
- Import MMM Monster Deck JSON into a MONSTER set.
- Import and render MMM worksheet JSON.
- Preserve MMM source ids such as `PLY-G1-001`, `LOOT-G1-001`, and `MON-G1-001` as CardForge card keys where possible.
- Render whole sets with placeholder or locked art.
- Export print-sheet PNGs and a collected game package.

## Main commands

```bash
cardforge import mmm magic_math_monsters \
  --player-deck MMM_Player_Deck_G1_Core_120_Cards_v4_simple_rules.json \
  --loot MMM_Loot_Insert_Cards_Core_v4_simple_rules.json \
  --monsters MMM_Monster_Deck_Core_v4_simple_rules.json \
  --worksheets MMM_Worksheet_Pad_G1_36_Pages_v4_simple_rules.json \
  --replace-existing

cardforge render set magic_math_monsters PLAYER --placeholder-art
cardforge render set magic_math_monsters MONSTER --placeholder-art

cardforge export print-sheets magic_math_monsters PLAYER
cardforge export print-sheets magic_math_monsters MONSTER
cardforge worksheet render magic_math_monsters
cardforge export game-package magic_math_monsters
```

## Design notes

The implementation keeps MMM as a project-level import/export mode, rather than changing CardForge into a single-purpose MMM app. Imported MMM cards are still normal CardForge cards, so existing review, render, art, and export systems can keep working.
