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

## Still intentionally deferred until live integrations

- Live LM Studio card generation and review prompts.
- Live ComfyUI workflow registry/patching/output routing.
- Image-to-image art reroll and repair workflows.
- Full web UI pages.
- PDF/PNG sheet exporters beyond current JSON export foundation.
- Worker queue/resume execution layer.
