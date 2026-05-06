# Live integration preparation

CardForge keeps LM Studio and ComfyUI behind small integration boundaries so the app remains testable without either service running.

## LM Studio

The existing batch pipeline already supports both offline packet generation and live LM Studio calls through `CardBatchService.generate_batch(..., use_mock=False)`.  The live call still goes through the same prompt package, LLM request log, robust packet parser, validation, and review queue used by mock output.

Environment variables:

```bash
CARDFORGE_LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
CARDFORGE_LMSTUDIO_MODEL=local-cardforge-model
CARDFORGE_LMSTUDIO_REVIEW_MODEL=local-cardforge-review-model
CARDFORGE_LMSTUDIO_TIMEOUT_SECONDS=300
CARDFORGE_LMSTUDIO_MAX_TOKENS=4096
```

Manual health:

```bash
cardforge llm health
cardforge llm test-prompt "Create one common necromancer creature idea."
```

## ComfyUI

The Comfy path is now split into two phases:

1. **Prepare**: offline-safe; writes a patched workflow and `comfy_jobs` row.
2. **Submit**: live path; sends the patched workflow to a running ComfyUI instance.

Default workflow sync:

```bash
cardforge comfy sync-workflows
cardforge comfy workflows
cardforge comfy validate-workflow stub.card_art.t2i.v1
```

Prepare a card art workflow without requiring ComfyUI:

```bash
cardforge comfy prepare-card-art gravebound_test CARD_0001
```

Queue the same work:

```bash
cardforge job enqueue-comfy-art gravebound_test CARD_0001 --prepare-only
cardforge job run-next gravebound_test
```

Live submit is intentionally explicit:

```bash
cardforge job enqueue-comfy-art gravebound_test CARD_0001 --submit
```

## Why prepare-only matters

Prepare-only workflows let automated tests verify:

- workflow registry sync
- patch point validation
- patched JSON generation
- prompt injection
- seed/dimension/save-prefix injection
- DB records and manifests

without making network calls or requiring a GPU process.
