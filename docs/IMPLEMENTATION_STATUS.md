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

