# Magic, Math, & Monsters first import dataset

This directory is reserved for the complete Magic, Math, & Monsters CardForge import dataset.

The full first-import package was prepared as a generated artifact because the normalized JSON files are large, especially the 120-card Player Deck file.

## Dataset counts

- 120 Player Deck spell cards
- 30 Player Deck loot insert cards
- 30 Monster Deck cards
- 36 worksheet / puzzle pages
- 47 story nodes
- Rulebook, Adventure Book, encounter map, validation report, and run scripts

## Expected package files

Place the generated package contents here before running the first import:

```text
imports/MMM_Player_Deck_G1_Core_CardForge_Import_v1.json
imports/MMM_Loot_Insert_Cards_CardForge_Import_v1.json
imports/MMM_Monster_Deck_Core_CardForge_Import_v1.json
imports/MMM_Worksheet_Pad_G1_CardForge_Import_v1.json
imports/MMM_Story_Nodes_CardForge_Reference_v1.json
imports/MMM_Encounter_Map_CardForge_Reference_v1.json
MMM_CardForge_Project_Import_Manifest_v1.json
MMM_CardForge_Batch_Runbook_v1.json
commands/RUN_FIRST_IMPORT.sh
commands/RUN_RENDER_AND_EXPORT.sh
validation/MMM_Import_Data_Validation_Report_v1.json
```

## First import command

```bash
cardforge db init
cardforge import mmm magic_math_monsters \
  --player-deck sample_mmm_input/imports/MMM_Player_Deck_G1_Core_CardForge_Import_v1.json \
  --loot sample_mmm_input/imports/MMM_Loot_Insert_Cards_CardForge_Import_v1.json \
  --monsters sample_mmm_input/imports/MMM_Monster_Deck_Core_CardForge_Import_v1.json \
  --worksheets sample_mmm_input/imports/MMM_Worksheet_Pad_G1_CardForge_Import_v1.json \
  --replace-existing
```

## Render/export command

```bash
cardforge render set magic_math_monsters PLAYER --placeholder-art
cardforge render set magic_math_monsters MONSTER --placeholder-art
cardforge export png magic_math_monsters PLAYER
cardforge export png magic_math_monsters MONSTER
cardforge export print-sheets magic_math_monsters PLAYER
cardforge export print-sheets magic_math_monsters MONSTER
cardforge worksheet render magic_math_monsters
cardforge worksheet export magic_math_monsters
cardforge export game-package magic_math_monsters
```
