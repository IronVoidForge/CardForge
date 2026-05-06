# Offline-buildable phases

CardForge is intentionally useful without LM Studio or ComfyUI running. The app treats local models as replaceable workers behind deterministic services, parsers, and manifests.

## Phases that can be completed without LM Studio

- **Phase 0: App skeleton and architecture guardrails** — settings, CLI, DB bootstrap, file safety, project scaffold.
- **Phase 1: Database schema and migrations/bootstrap** — all durable state tables and service boundaries.
- **Phase 2: Project, set, and registry foundation** — default card type, keyword, template, and export registries.
- **Phase 3: Card schema, markdown, and manual creation** — canonical JSON, human markdown, versions, validation.
- **Phase 4 offline part: LLM request logging, prompt packages, and parsers** — prompt templates, rendered prompt packages, prompt/response logs, robust packet parser, JSON salvage, markdown table/headed-block salvage. Real LM Studio calls remain a manual integration test.
- **Phase 5 offline part: Batch generation** — deterministic simulated card batches produce the same packet shape real LM Studio will produce later.
- **Phase 6: Deterministic validation, autofill, and text repair** — required fields, registry checks, keyword checks, text length warnings, offline autofill, offline rules text repair.
- **Phase 7 offline part: Balance/rules/auto review** — curve, type mix, rarity mix, keyword density, stat sanity, rules wording lint, card text auto-review, art candidate auto-review, and auto-refinement using simulated LLM packets.
- **Phase 8: Placeholder/locked-art renderer** — Pillow front/back rendering, previews, layout reports.
- **Phase 9 offline part: API/UI can be developed against DB/files** — no model service needed, because batches/art can be simulated.
- **Phase 10 offline part: Art prompt/candidate pipeline** — art prompts, dummy image candidates, candidate manifests, review queue. Real ComfyUI execution remains a manual integration test.
- **Phase 11: Review/rejection/rework loop** — approve/reject/lock, rework requests, failure tags, offline text repair.
- **Phase 12 offline part: Final render review** — cards can render with placeholder or locked dummy art.
- **Phase 13 offline part: JSON/CSV/PNG exports** — export logic can operate on rendered assets.
- **Phase 14 offline part: Job/resume design** — workers can run mocked jobs; real model jobs remain integration tests.
- **Phase 15: Packaging/regression tests** — automated tests should continue to use simulated model outputs.

## Phases that need live LM Studio or ComfyUI only for final integration tests

- Real LM Studio card generation, balance critique, rules critique, and prompt repair.
- Real ComfyUI image generation, image-to-image rerolls, workflow patching, and output routing.

## Current offline commands

```bash
cardforge batch generate gravebound_test SET001 --count 12 --request "Generate gothic necromancer cards."
cardforge batch validate gravebound_test BATCH_0001
cardforge batch balance-review gravebound_test BATCH_0001
cardforge batch rules-review gravebound_test BATCH_0001
cardforge batch auto-review gravebound_test BATCH_0001
cardforge card autofill gravebound_test CARD_0001
cardforge card refine gravebound_test CARD_0001
cardforge rework repair-rules gravebound_test CARD_0001 --reason "shorten for template"
cardforge art prompt gravebound_test CARD_0001
cardforge art generate-dummy gravebound_test CARD_0001 --count 4
cardforge art approve gravebound_test ART_CAND_0001
cardforge art lock gravebound_test ART_CAND_0001
cardforge render card gravebound_test CARD_0001 --no-placeholder-art
```

## Parser policy

All model-like output, including simulated output, goes through the same boundary:

1. CardForge packet parser.
2. JSON salvage parser.
3. Markdown table parser.
4. Markdown heading-block parser.
5. Schema coercion and deterministic validation.

That mirrors the robust FilmCreator packet/markdown approach and prevents a bad raw model response from directly mutating canonical cards.
