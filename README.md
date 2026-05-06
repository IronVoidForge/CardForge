# CardForge

CardForge is a local-first Python pipeline for generating, reviewing, rendering, and exporting custom trading-card-style game cards.

This repository is a new app inspired by the FilmCreator pipeline architecture: small services, SQL-backed state, file-backed artifacts, local LM Studio text generation hooks, ComfyUI image generation hooks, review/rejection/rework flows, deterministic rendering, and resumable operator workflows.

## Current vertical slice

This initial repo contains the first working foundation:

- SQLite database with schema migration/bootstrap.
- Project and set creation.
- File scaffold under a workspace folder.
- Manual card creation.
- Card version history.
- Deterministic validation.
- Placeholder card front/back rendering with Pillow.
- Review item creation and decisions.
- CLI commands built with Typer.
- Stubbed LM Studio and ComfyUI integration classes.
- Automated tests for DB, scaffolding, validation, rendering, and review flow.

## Install for local development

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Quick start

```bash
cardforge db init
cardforge project create gravebound_test --name "Gravebound Test"
cardforge set create gravebound_test --name "Gravebound Dominion"
cardforge card create gravebound_test SET001 --name "Bone Lantern Warden" --type creature --rules-text "Guard. When this dies, draw a card." --attack 2 --health 4
cardforge card validate gravebound_test CARD_0001
cardforge render card gravebound_test CARD_0001 --placeholder-art
cardforge review list gravebound_test
cardforge export json gravebound_test SET001
```

The default workspace is `./workspace`. Override it with:

```bash
export CARDFORGE_WORKSPACE=/path/to/workspace
```

## Planned phases

See `docs/PHASE_PLAN.md` for the full implementation roadmap, including automated and manual test points.

## Local integrations

Environment variables reserved for local model hooks:

```bash
CARDFORGE_LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
CARDFORGE_LMSTUDIO_MODEL=your-model
CARDFORGE_LMSTUDIO_REVIEW_MODEL=your-review-model
CARDFORGE_LMSTUDIO_TIMEOUT_SECONDS=300

CARDFORGE_COMFY_BASE_URL=http://127.0.0.1:8188
CARDFORGE_COMFY_INPUT_DIR=C:\ComfyUIInstall\input
CARDFORGE_COMFY_OUTPUT_DIR=C:\ComfyUIInstall\output
CARDFORGE_COMFY_TIMEOUT_SECONDS=1800
```

The current classes are intentionally thin and testable. They do not require LM Studio or ComfyUI during automated tests.
