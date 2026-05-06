# Refactoring pass: structure and responsibility cleanup

This pass did not add new user-facing pipeline behavior. It reorganized code so the next phases can grow without turning into a monolith.

## What changed

### CLI command split

The Typer entrypoint is now only a command registry:

```text
src/cardforge/cli/main.py
src/cardforge/cli/bootstrap.py
src/cardforge/cli/commands/
  art.py
  auto.py
  batches.py
  cards.py
  db.py
  exports.py
  integrations.py
  projects.py
  prompts.py
  render.py
  review.py
  rework.py
  sets.py
```

Each command module owns one operator area. Shared command helpers live in `cli/bootstrap.py`.

### Card service split

`CardService` still owns card state transitions, but low-level responsibilities moved out:

```text
services/cards/card_file_writer.py
  Writes card.json and card.md artifacts.

services/cards/card_version_service.py
  Appends immutable card_versions rows.
```

This keeps card creation/update paths smaller and makes file-writing/version-writing independently testable.

### Batch parsing split

Card batch generation now delegates LLM packet payload coercion to:

```text
services/batches/card_payload_parser.py
```

`CardBatchService` now handles orchestration: create batch, render prompt package, call mock/live model, persist artifacts, create cards, validate, and enqueue review. It no longer owns card payload coercion.

### Prompt/default scaffold split

Large project defaults moved out of the scaffold implementation:

```text
services/projects/defaults.py
services/projects/project_scaffold.py
```

The scaffold now only creates folders and writes default artifacts. The default registries and prompt template bodies are isolated.

### Auto-review split

Auto-review is now split into orchestration, scoring, and persistence:

```text
services/review/auto_review_service.py
services/review/auto_review_heuristics.py
services/review/auto_review_report_store.py
```

The heuristic reviewer remains deterministic and offline-safe. A later LM Studio reviewer can replace or supplement the heuristic reviewer behind the same report shape.

### Parser split while preserving compatibility

The robust FilmCreator-style flexible parser was split by responsibility:

```text
services/llm/packet_types.py
services/llm/packet_sections.py
services/llm/packet_core.py
services/llm/card_record_salvage.py
services/llm/packet_parser.py
```

`packet_parser.py` remains a compatibility facade, so existing imports keep working. The parser still supports:

1. Tagged CardForge packets.
2. JSON object/list salvage.
3. Markdown table salvage.
4. Markdown heading-block salvage.

### Database schema split

The large SQL statement list moved to:

```text
db/table_definitions.py
```

`db/schema.py` now owns migration/reset execution rather than storing all table definitions inline.

## Test results

After the refactor:

```text
18 passed
```

Manual smoke path also passed with offline dummy/simulated data:

```bash
python -m cardforge db init
python -m cardforge project create gravebound_test --name "Gravebound Test"
python -m cardforge set create gravebound_test --name "Gravebound Dominion"
python -m cardforge batch generate gravebound_test SET001 --count 3 --request "Generate gothic necromancer cards."
python -m cardforge batch auto-review gravebound_test BATCH_0001
python -m cardforge art generate-dummy gravebound_test CARD_0001 --count 1
python -m cardforge render card gravebound_test CARD_0001
python -m cardforge project status gravebound_test
```

## Still worth refactoring later

The next cleanup passes should target:

- SQL repository classes for cards, batches, art, renders, and reviews.
- A dedicated export service instead of CLI-local JSON export logic.
- A template registry service before the visual template editor work.
- Job queue services before live ComfyUI/LM Studio long-running tasks.
