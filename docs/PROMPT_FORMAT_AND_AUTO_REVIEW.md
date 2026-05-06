# Prompt format, autofill, refinement, and auto-review

This pass adds the CardForge prompt-package layer that sits between app state and LM Studio. It is intentionally offline-safe: the same prompt templates, package logs, parser, schema coercion, and review records are used whether the response comes from a deterministic simulator or a live local model.

## Prompt package format

Prompt templates live inside each project:

```text
projects/<project_slug>/prompt_templates/
  CARDFORGE_PROMPT_FORMAT.md
  card_batch_generation_v1.md
  card_autofill_v1.md
  card_refinement_v1.md
  auto_review_v1.md
```

Templates are markdown documents with flexible normalized headings:

```markdown
# Title
Card Autofill v1

# ID
card_autofill_v1

# Task
card_autofill

# Model Role
You complete missing card fields without changing the card's identity.

# Inputs
- project_slug: {project_slug}
- card_key: {card_key}
- missing_fields: {missing_fields}

# Instructions
Fill only missing or weak fields.

# Output Contract
Return one CARDFORGE packet.

# Packet Shape
[[CARDFORGE_PACKET]]
task: card_autofill
version: 1
...

# Sources
- card.json
- validation report
```

The parser accepts `#` through `######` headings, normalized section names, and `- key: value` inputs. Rendered prompt packages are written to:

```text
projects/<project_slug>/prompt_packages/PROMPT_0001/
  prompt_package.md
  system_prompt.md
  user_prompt.md
```

The SQL tables `prompt_packages` and `llm_requests` keep the reproducibility trail.

## Model response policy

All model-shaped output goes through the same boundary:

1. Tagged `CARDFORGE_PACKET` parser.
2. JSON salvage parser.
3. Markdown table salvage parser.
4. Markdown heading-block salvage parser.
5. Schema coercion.
6. Deterministic validation.

That mirrors the robust FilmCreator packet/markdown approach and prevents raw model text from directly mutating canonical cards.

## Autofill

Autofill completes missing fields while preserving card identity:

```bash
cardforge card autofill gravebound_test CARD_0001
```

Offline mode returns a deterministic `card_autofill` packet and updates only missing fields by default. Use `--force` to allow replacement of existing fields. Future live use can pass `--live` after LM Studio is available.

Autofill currently fills:

```text
type_line
rules_text
flavor_text
design_notes
art_direction
template_id
creature/legendary attack and health
keywords when empty
```

## Auto-review

Auto-review writes both JSON and markdown reports and stores an `auto_reviews` row:

```bash
cardforge card auto-review gravebound_test CARD_0001
cardforge batch auto-review gravebound_test BATCH_0001
cardforge art auto-review gravebound_test ART_CAND_0001
```

Card text review checks:

```text
validation errors and warnings
rules text length/template fit risk
ambiguous wording patterns
missing art direction
punctuation/readability
```

Art candidate review checks:

```text
image file exists
candidate status
locked/rejected state
dummy/offline candidate marker
```

Statuses:

```text
strong_pass
needs_human_review
needs_rework
```

Auto-review reports open normal or high-severity review items when human action is needed.

## Refinement

Refinement runs autofill, auto-review, and a model-shaped repair pass:

```bash
cardforge card refine gravebound_test CARD_0001
cardforge auto refine-card gravebound_test CARD_0001
```

Offline refinement returns a deterministic `card_refinement` packet. Live refinement will use the same `card_refinement_v1` prompt package and parser path.

Refinement currently targets:

```text
missing fields
rules text too long
ambiguous words like "thing" or "stuff"
"any card" without zone/type context
missing punctuation
missing art direction
```
