# CardForge Engineering Guide

CardForge is a local-first Python app for generating, reviewing, rendering, and exporting custom cards.

## Engineering principles

- Keep modules small and focused.
- Do not bypass service boundaries from CLI or UI handlers.
- Do not write project files outside `AssetStore`.
- Do not let raw LLM output mutate canonical cards without parsing and validation.
- Do not call live LM Studio or ComfyUI in automated tests.
- Prefer deterministic offline simulations for tests.
- Preserve append-only history for card versions, review decisions, and audit events.

## Required checks

Run before committing:

```bash
make quality
```

Manual smoke path:

```bash
cardforge db init
cardforge project create gravebound_test --name "Gravebound Test"
cardforge set create gravebound_test --name "Gravebound Dominion"
cardforge job enqueue-batch-generate gravebound_test SET001 --count 3 --request "Generate gothic necromancer cards."
cardforge job run-all gravebound_test
cardforge resume plan gravebound_test
cardforge project status gravebound_test
```

## Sensitive areas

Be extra careful with:

- SQLite schema changes
- path resolution and asset serving
- prompt packet parsing
- review/rework state transitions
- generation job retries
- render/export path routing
- future live LM Studio/ComfyUI adapters
