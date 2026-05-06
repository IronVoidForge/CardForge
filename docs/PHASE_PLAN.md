# CardForge phase plan

## Milestone 1: Local app foundation

### Phase 0: App skeleton and architecture guardrails

Build the repo layout, settings, DB bootstrap, project scaffold, status service, and CLI entrypoint.

Automated tests:

- settings load defaults
- workspace path creation
- project slug validation
- asset store rejects path traversal
- project scaffold creates expected folders
- database opens and initializes

Manual tests:

```bash
cardforge --help
cardforge db init
cardforge project create gravebound_test
cardforge project status gravebound_test
```

### Phase 1: Database schema and migrations

Create SQLite tables for projects, sets, cards, card versions, batches, LLM requests, jobs, art candidates, templates, renders, reviews, rework requests, exports, and audit events.

Automated tests:

- schema bootstrap creates all expected tables
- project CRUD
- set CRUD
- card CRUD
- card version append-only behavior
- review decision append-only behavior
- uniqueness constraints

Manual tests:

```bash
cardforge db reset --yes
cardforge db init
cardforge project create gravebound_test
cardforge set create gravebound_test --name "Gravebound Dominion"
```

### Phase 2: Project, set brief, registries

Add set briefs, default card type registry, keyword registry, faction registry, template registry, and export settings.

Automated tests:

- set brief save as markdown and JSON
- default registries validate
- card type required fields enforced
- unknown keyword fails validation

Manual tests:

```bash
cardforge registry list-card-types gravebound_test
cardforge registry validate gravebound_test
```

### Phase 3: Card schema, markdown, manual card creation

Create canonical card JSON and human-readable markdown. Manual card creation must work before LLM generation.

Automated tests:

- manual card creation
- card markdown written
- card version created on edit
- validation catches missing required fields
- validation catches invalid stats for card types
- slug deduplication

Manual tests:

```bash
cardforge card create gravebound_test SET001 --name "Bone Lantern Warden" --type creature --rules-text "Guard."
cardforge card validate gravebound_test CARD_0001
```

## Milestone 2: Text generation pipeline

### Phase 4: LM Studio integration and response logging

Add `LMStudioClient`, prompt builders, packet parser, JSON repair, and LLM request records. Automated tests use mocked HTTP responses.

Manual tests:

```bash
cardforge llm health
cardforge llm test-prompt "Return one gothic creature card idea."
```

### Phase 5: Batch card generation

Generate 10-15 cards from a set request. Save raw response, parsed JSON, cards, versions, validation reports, and review items.

Manual tests:

```bash
cardforge batch generate gravebound_test SET001 --count 12 --request request.md
cardforge batch validate gravebound_test BATCH_0001
```

### Phase 6: Deterministic validation, layout fit, text repair

Add rules text linting, layout fit estimation, and LLM-powered repair requests.

Manual tests:

```bash
cardforge card repair gravebound_test CARD_0001 --type rules_text_repair --reason text_too_long
cardforge card compare-versions gravebound_test CARD_0001
```

### Phase 7: Balance and rules review

Add deterministic curve/type/rarity analysis plus LLM balance and rules review.

Manual tests:

```bash
cardforge batch balance-review gravebound_test BATCH_0001
cardforge batch rules-review gravebound_test BATCH_0001
```

## Milestone 3: Rendering pipeline

### Phase 8: Template system and placeholder renderer

Add template registry, text layout engine, symbol service, and deterministic card front/back rendering.

Manual tests:

```bash
cardforge render card gravebound_test CARD_0001 --placeholder-art
cardforge render batch gravebound_test BATCH_0001 --placeholder-art
```

### Phase 9: FastAPI/operator UI MVP

Add dashboard, set detail, batch detail, card detail/edit, review queue, and render preview pages.

Manual tests:

```bash
cardforge ui gravebound_test
```

## Milestone 4: Image generation pipeline

### Phase 10: ComfyUI workflow registry and art generation

Add Comfy client, workflow registry, workflow patcher, image job service, output router, art prompts, and art candidate records.

Manual tests:

```bash
cardforge comfy health
cardforge art generate gravebound_test CARD_0001 --candidates 4 --execute
```

### Phase 11: Art review, rejection, and rework loop

Add approve/reject/lock, failure tags, reroll with notes, and image-to-image rework requests.

Manual tests:

```bash
cardforge art reject gravebound_test ART_CAND_0001 --reason "Wrong style" --tag wrong_style
cardforge art rework gravebound_test CARD_0001 --from-rejection ART_CAND_0001
```

## Milestone 5: Finalization pipeline

### Phase 12: Final render review and card locking

Require approved text, locked art, clean render, no blocking review items, and current render before final lock.

Manual tests:

```bash
cardforge render card gravebound_test CARD_0001
cardforge card lock gravebound_test CARD_0001
```

### Phase 13: Export system

Export PNG, JSON, CSV, PDF sheets, markdown catalogs, and tabletop assets.

Manual tests:

```bash
cardforge export json gravebound_test SET001
cardforge export png gravebound_test SET001
```

### Phase 14: Worker queue and resumability

Add durable jobs, retry, stale-running detection, resume plans, and crash recovery.

Manual tests:

```bash
cardforge jobs list gravebound_test
cardforge resume gravebound_test SET001
```

### Phase 15: Polish, packaging, and full regression tests

Add sample project, sample templates, docs, backup/import/export project commands, and full mocked end-to-end tests.

Manual full-path test:

1. Create project.
2. Create set.
3. Generate 12 cards.
4. Validate batch.
5. Repair one card.
6. Balance review.
7. Render with placeholder art.
8. Generate art for one card.
9. Lock art.
10. Render final card.
11. Approve and lock card.
12. Export PNG and JSON.
