# Implementation status after offline phase pass

This pass extends CardForge beyond the initial manual-card vertical slice while keeping LM Studio and ComfyUI optional.

## Completed offline work

- Robust CardForge/FilmCreator-style packet parsing.
- JSON response salvage.
- Markdown table response salvage.
- Markdown heading/block response salvage.
- Deterministic simulated card batch generation.
- Batch raw-response logging and parsed JSON artifacts.
- LLM request records and prompt/response log files for simulated calls.
- Batch validation reports.
- Deterministic balance review reports.
- Deterministic rules wording review reports.
- Offline rules text rework/repair with card version history.
- Art prompt creation from card data.
- Dummy art candidate generation that simulates ComfyUI image outputs.
- Art approve/reject/lock lifecycle.
- Rendering with placeholder art or locked dummy art.
- Expanded project status counts for batches, art candidates, locked art, renders, and open review items.

## Automated test coverage

Current test suite covers:

- DB/project scaffold and path safety.
- Manual card creation, validation, markdown/JSON file output, and rendering.
- Packet parser section parsing.
- Markdown table salvage parsing.
- Markdown heading/block salvage parsing.
- Simulated batch generation and artifact writing.
- Balance review and offline repair.
- Dummy art generation, approval/locking, and render with locked art.

## Manual smoke path

The following path was manually exercised with no live LM Studio or ComfyUI:

```bash
python -m cardforge db init
python -m cardforge project create gravebound_test --name Test
python -m cardforge set create gravebound_test --name "Gravebound Dominion"
python -m cardforge batch generate gravebound_test SET001 --count 3 --request "Make gothic necromancer cards"
python -m cardforge batch balance-review gravebound_test BATCH_0001
python -m cardforge batch rules-review gravebound_test BATCH_0001
python -m cardforge art generate-dummy gravebound_test CARD_0001 --count 2
python -m cardforge art approve gravebound_test ART_CAND_0001
python -m cardforge art lock gravebound_test ART_CAND_0001
python -m cardforge render card gravebound_test CARD_0001 --no-placeholder-art
python -m cardforge project status gravebound_test
```


## Completed in the prompt/autofill/auto-review pass

- Project-scaffolded prompt format guide and prompt templates.
- Prompt package renderer with markdown section parsing and reproducible package files.
- SQL state for prompt packages and auto reviews.
- Batch generation now uses the prompt-template/package layer before simulated or live LLM calls.
- Card autofill service for missing type line, rules, flavor, design notes, art direction, template, keywords, and creature stats.
- Card auto-review service with score, findings, recommendations, JSON/markdown reports, and review queue creation.
- Art candidate auto-review service with score JSON stored on candidates.
- Card refinement service that runs autofill, auto-review, and a model-shaped repair packet.
- CLI commands for `prompt`, `card autofill`, `card refine`, `card auto-review`, `batch auto-review`, `art auto-review`, and `auto refine-card`.

## Still intentionally deferred until live integrations

- Live LM Studio card generation and review prompts.
- Live ComfyUI workflow registry/patching/output routing.
- Image-to-image art reroll and repair workflows.
- Full web UI pages.
- PDF/PNG sheet exporters beyond current JSON export foundation.
- Worker queue/resume execution layer.

## Completed in the refactoring/cleanup pass

- Split the Typer CLI into focused command modules under `cli/commands`.
- Extracted card file writing and card version appending out of `CardService`.
- Extracted card payload coercion out of `CardBatchService`.
- Split project scaffold defaults from scaffold behavior.
- Split auto-review into orchestration, deterministic heuristics, and report persistence.
- Split the robust parser into packet core, section normalization, card-record salvage, and a compatibility facade.
- Moved SQL table definitions out of the migration executor.
- Added structural regression tests for the CLI composition and parser extraction.

Current automated tests after cleanup: `18 passed`.

## V5 local UI and exports

Added in the latest pass:

- FastAPI/Jinja local operator UI with polished responsive styling.
- Project dashboard, set detail, batch detail, card editor, art candidate review, render actions, and review queue pages.
- Safe workspace asset serving for generated art and rendered cards.
- CLI command: `cardforge ui serve --host 127.0.0.1 --port 8765`.
- Export service and CLI commands for JSON, CSV, Markdown catalog, and PNG render bundles.
- Tests for the web UI, simulated batch generation through the UI, locked-art rendering, review pages, and exports.


## V6 jobs, resume, observability, and quality gates

Added in this pass:

- Local `generation_jobs` queue with enqueue, run-next, run-all, retry, and stale requeue operations.
- Offline job dispatcher for batch generation, validation, auto-review, card autofill/refinement, dummy art, art auto-review, rendering, and exports.
- Read-only resume planner that recommends the next safe action and can queue one suggested job.
- Job dashboard in the web UI at `/projects/<project_slug>/jobs`.
- Health endpoint at `/healthz`.
- CLI diagnostics via `cardforge doctor check`.
- Append-only audit events for job enqueue/start/complete/fail/retry.
- Project status now includes pending/running/failed job counts and the resume plan.
- Accessibility/UI polish: skip link, focus-visible styling, jobs navigation, reduced-motion handling, and responsive data tables.
- Quality gate scripts, Makefile targets, GitHub Actions CI workflow, and project `AGENTS.md` engineering guide.
- Automated tests for jobs, retry, resume planning, diagnostics, health endpoint, and jobs UI.

Current automated tests after this pass: `26 passed`.

Current local quality gate:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/quality_check.py
```

This environment does not have `ruff` installed, so the local quality script skips Ruff. CI installs dev dependencies and runs the strict quality gate.

## v8 Live integration preparation and workflow registry

Added the next offline-safe integration phase:

- Comfy workflow registry service backed by SQL and workspace JSON
- declarative Comfy patch points and safe workflow patcher
- default stub Card Art T2I API workflow
- prepare-only Comfy card art job service
- optional live submit path behind explicit `submit=True`
- job queue support for `art_prepare_comfy` and `art_submit_comfy`
- CLI commands for Comfy workflow sync/list/validate/prepare
- integrations dashboard page for LM Studio/ComfyUI configuration, workflows, and prepared jobs
- card detail action to prepare a Comfy workflow without running ComfyUI
- tests for workflow sync, patching, prepare-only jobs, job dispatch, and integration UI

The default test path still requires no LM Studio or ComfyUI connection.

## Latest: Labs

Added CardForge Prompt Lab and Image Lab. These are adapted from FilmCreator's lab pattern: create isolated cases, run attempts, compare outputs, mark accepted/rejected work, and write promotion/recommendation notes without mutating production artifacts.

- Prompt Lab: `cardforge lab prompt ...`
- Image Lab: `cardforge lab image ...`
- UI: `/projects/<project_slug>/labs`
- Queue: `prompt_lab_run` and `image_lab_run` jobs

See `docs/LABS_AND_REMAINING_PIPELINE.md`.

## v10 Lab promotion gates and prompt template versioning

Added the next lab-to-production control layer:

- Prompt template SQL/file versioning with seeded `v001` active versions.
- `cardforge prompt sync` and `cardforge prompt version ...` commands.
- Review-gated Prompt Lab promotion requests.
- Approved Prompt Lab promotions can create and activate new prompt-template versions.
- Image Lab art-prompt promotion requests with evidence bundles and manual-application safety.
- Prompt Lab and Image Lab A/B `score_100` metrics.
- Labs UI now shows promotion requests and prompt template versions.
- Tests cover version seeding, promotion gating, promotion application, image-lab guidance requests, and UI visibility.

Current quality gate result in this environment:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/quality_check.py
# 42 passed; ruff skipped locally because it is not installed
```

See `docs/LAB_PROMOTION_AND_PROMPT_VERSIONING.md`.



## v11 Mobile operator pivot

CardForge now treats the phone/tablet as the primary operator UI while the workstation runs Python, SQLite, LM Studio, ComfyUI, files, renders, and exports.

Added in this pass:

- Mobile-first `/m` UI surface for project dashboard, review queue, card inspection, and jobs.
- PWA manifest, service worker shell, SVG icon, and mobile install metadata.
- `cardforge mobile serve` command for LAN/VPN mobile operation.
- `cardforge mobile launcher` command that writes a clickable HTML launcher file for phones/tablets.
- Optional password login with signed sessions and CSRF protection for mutating form posts.
- Mobile-friendly bottom navigation, sticky action controls, tap-sized buttons, responsive cards, and image zoom links.
- Mobile auth/session/launcher tests.
- CI and Makefile updated to run format, compile, lint, and tests as separate repeatable gates.

Current local gate verified in this environment:

```bash
make quality
# 45 passed; ruff skipped locally because it is not installed
```

See `docs/MOBILE_OPERATOR_REQUIREMENT.md`.
