# CardForge

CardForge is a local-first Python pipeline for generating, reviewing, rendering, and exporting custom trading-card-style game cards.

This repository is a new app inspired by the FilmCreator pipeline architecture: small services, SQL-backed state, file-backed artifacts, local LM Studio text generation hooks, ComfyUI image generation hooks, review/rejection/rework flows, deterministic rendering, and resumable operator workflows.

## Current vertical slice

This repo now contains the first offline-safe production slice:

- SQLite database with schema migration/bootstrap.
- Project and set creation.
- File scaffold under a workspace folder.
- Manual card creation.
- Card version history.
- Robust CardForge/FilmCreator-style packet parsing plus JSON/table/heading markdown salvage.
- Deterministic simulated batch generation for 10-15 card tests without LM Studio.
- Raw response, parsed JSON, LLM request logs, batch manifests, validation reports, balance reports, and rules review reports.
- Deterministic validation, text repair/rework, balance review, rules wording review, prompt-package rendering, autofill, refinement, and auto-review.
- Art prompt creation, dummy image candidate generation without ComfyUI, and art candidate auto-review.
- Approve/reject/lock lifecycle for art candidates.
- Placeholder or locked-art card front/back rendering with Pillow.
- Review item creation and decisions.
- Local job queue, resume planner, diagnostics, health endpoint, and audit events.
- Mobile-first FastAPI/Jinja operator UI with PWA manifest, login protection, jobs, review, card, batch, lab, and export pages.
- Quality gate scripts, Makefile targets, and GitHub Actions CI workflow.
- CLI commands built with Typer.
- Stubbed live LM Studio and ComfyUI integration classes for later manual integration.
- Automated tests for DB, scaffolding, parsing, simulated generation, validation, balance, rework, art, rendering, and review flow.

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

# Offline simulated LM output through the real parser/validation path.
cardforge batch generate gravebound_test SET001 --count 12 --request "Generate gothic necromancer cards."

# Queue-based equivalent for long-running work.
cardforge job enqueue-batch-generate gravebound_test SET001 --count 12 --request "Generate gothic necromancer cards."
cardforge job run-all gravebound_test
cardforge resume plan gravebound_test
cardforge batch balance-review gravebound_test BATCH_0001
cardforge batch rules-review gravebound_test BATCH_0001
cardforge batch auto-review gravebound_test BATCH_0001

# Offline prompt/refinement path.
cardforge card autofill gravebound_test CARD_0001
cardforge card refine gravebound_test CARD_0001

# Offline simulated ComfyUI art candidates through the real review/render path.
cardforge art generate-dummy gravebound_test CARD_0001 --count 4
cardforge art auto-review gravebound_test ART_CAND_0001
cardforge art approve gravebound_test ART_CAND_0001
cardforge art lock gravebound_test ART_CAND_0001
cardforge render card gravebound_test CARD_0001 --no-placeholder-art

cardforge review list gravebound_test
cardforge export json gravebound_test SET001
cardforge export csv gravebound_test SET001
cardforge export markdown gravebound_test SET001
cardforge export png gravebound_test SET001

# Diagnostics and quality gates.
cardforge doctor check
make quality

# Optional local operator UI.
cardforge ui serve --mode desktop --host 127.0.0.1 --port 8765

# PC + mobile/tablet operator UI from the same workstation server.
cardforge ui serve --mode both --host 0.0.0.0 --port 8765 --password "choose-a-local-password"

# Generate click/double-click launcher files under workspace/launchers.
cardforge launcher write --host 192.168.1.42 --port 8765
```

The default workspace is `./workspace`. Override it with:

```bash
export CARDFORGE_WORKSPACE=/path/to/workspace
```

## Planned phases

See `docs/PHASE_PLAN.md` for the full implementation roadmap, `docs/OFFLINE_PHASES.md` for exactly which phases can be built and tested without live LM Studio or ComfyUI, `docs/PROMPT_FORMAT_AND_AUTO_REVIEW.md` for the prompt package/autofill/refinement/auto-review contract, `docs/MOBILE_OPERATOR_REQUIREMENT.md` for the mobile-first LAN/PWA workflow, `docs/PC_MOBILE_STARTERS_AND_INTEGRATIONS.md` for one-click launcher files and network API setup, `docs/UI_AND_EXPORTS.md` for the operator UI and export workflow, and `docs/JOBS_RESUME_AND_QUALITY.md` for the queue/resume/quality-gate layer.

## Local integrations

You can configure network API settings from `/projects/<project_slug>/integrations`, with `cardforge llm configure`, with `cardforge comfy configure`, or with environment variables:

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
