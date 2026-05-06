# Labs and Remaining Pipeline

CardForge now has the same lab idea as FilmCreator, adapted to cards:

- **Prompt Lab** isolates prompt-template experiments under `99_prompt_lab`.
- **Image Lab** isolates card-art prompt experiments under `99_image_lab`.
- Lab runs never mutate production cards, templates, art candidates, or renders.
- Accepted lab runs write promotion/recommendation notes so a human can intentionally apply only proven changes.

## Prompt Lab

Prompt Lab helps narrow down prompt types, output contracts, parser resilience, and card text instructions before changing production templates.

Typical flow:

```bash
cardforge lab prompt create gravebound_test card_batch_generation_v1 --target-type set --target-id SET001 --notes "Test lower-complexity common card wording."
cardforge lab prompt run gravebound_test PLAB_0001 --variant-notes "Prefer fewer triggered abilities and shorter rules text."
cardforge lab prompt compare gravebound_test PLAB_0001
cardforge lab prompt mark gravebound_test PLAB_0001 RUN_0001 accepted --notes "Cleaner type mix and shorter rules."
cardforge lab prompt promote-note gravebound_test PLAB_0001
```

Prompt Lab writes:

```text
projects/<project>/99_prompt_lab/cases/<case>/
  case_manifest.json
  context.json
  original_system_prompt.md
  original_user_prompt.md
  candidate_prompt.md
  runs/<run>/
    candidate_prompt.md
    raw_response.md
    parsed_response.json
    metrics.json
    run_manifest.json
  comparison.json
  comparison.md
projects/<project>/99_prompt_lab/promotion_notes/
```

## Image Lab

Image Lab helps test card-art prompt wording and composition families without creating production art candidates.

Typical flow:

```bash
cardforge lab image create gravebound_test CARD_0001 --notes "Compare centered portrait vs action composition."
cardforge lab image run gravebound_test ILAB_0001 --prompt-append "centered portrait, violet rim light" --count 4
cardforge lab image review gravebound_test ILAB_0001 ATT_0001 LAB_CAND_001 --decision accepted --rating 5 --success-tag readable_silhouette
cardforge lab image compare gravebound_test ILAB_0001
cardforge lab image recommend gravebound_test ILAB_0001 --notes "Promote violet rim light and centered portrait wording."
```

Image Lab writes:

```text
projects/<project>/99_image_lab/cases/<case>/
  case_manifest.json
  input_snapshot.json
  workback_notes.md
  attempts/<attempt>/
    prompt.md
    candidates/*.png
    candidate_manifest.json
    operator_review.json
    attempt_summary.md
  comparison.json
  comparison.md
  workback_recommendation.md
```

## Job queue support

Both lab run types can be queued:

```bash
cardforge job enqueue-prompt-lab-run gravebound_test PLAB_0001 --variant-notes "Make common cards simpler."
cardforge job enqueue-image-lab-run gravebound_test ILAB_0001 --prompt-append "candlelit foreground" --count 4
cardforge job run-all gravebound_test
```

## UI support

Open:

```text
/projects/<project_slug>/labs
```

The page can create prompt/image lab cases, run offline mock attempts, create promotion notes, and create recommendations.

## What remains in the broader pipeline

High-value remaining work:

1. **Lab promotion workflow**: turn promotion/recommendation notes into explicit reviewed template changes.
2. **Live LM Studio lab runs**: replace mock Prompt Lab runs with live LM Studio behind the same logged case/run boundary.
3. **Live Comfy Image Lab attempts**: add prepare-only and submit modes for lab attempts, still isolated from production art.
4. **Prompt template versioning**: add versioned prompt templates so accepted lab changes can be applied as new template versions.
5. **A/B scoring dashboards**: compare prompt variants by parse success, validation errors, text length, balance findings, and operator acceptance rate.
6. **Deck/set playtest loop**: generate sample decks, run deterministic checks, and later use LLM-assisted simulated playtest notes.
7. **Template Studio editing**: improve template editing in the UI beyond JSON text updates.
8. **Production promotion gates**: require tests, lab evidence, and human approval before changing default prompt templates or workflows.
9. **Live integration hardening**: Comfy history polling/output routing and LM Studio response error recovery.
10. **Import/export polish**: spreadsheet imports, Tabletop Simulator deck sheets, print bleed/safe-zone reports.

The current offline path remains fully testable without LM Studio or ComfyUI.
