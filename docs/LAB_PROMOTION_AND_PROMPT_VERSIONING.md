# Lab promotion gates and prompt template versioning

CardForge labs are intentionally isolated from production. A Prompt Lab or Image Lab run can produce useful evidence, but it cannot silently change production cards, prompt templates, or art prompts.

This phase adds a controlled promotion path:

```text
lab case -> accepted run/attempt -> promotion request -> review approval -> controlled application
```

## Prompt template versions

Project prompt templates are mirrored into SQL and seeded with an initial active version.

```bash
cardforge prompt sync <project_slug>
cardforge prompt version list <project_slug>
```

Version files live under:

```text
projects/<project_slug>/prompt_templates/versions/<template_key>/<template_key>_v001.md
```

A version can be:

```text
active
proposed
approved
rejected
```

Only an `approved` or already `active` version can be activated. Activating a version writes its markdown back to the active project template file and marks older versions for the same template as inactive.

## Prompt Lab promotion

Prompt Lab runs must be marked `accepted` before they can become promotion requests.

```bash
cardforge lab prompt create gravebound_test card_refinement_v1 --target-type card --target-id CARD_0001
cardforge lab prompt run gravebound_test PLAB_0001 --variant-notes "Keep rules short."
cardforge lab prompt mark gravebound_test PLAB_0001 RUN_0001 accepted --notes "Good compact rules contract."
cardforge lab prompt promote-request gravebound_test PLAB_0001 --notes "Use the short rules guidance."
```

Promotion requests are reviewable:

```bash
cardforge lab promotion list gravebound_test
cardforge lab promotion approve gravebound_test PROMO_0001 --notes "Evidence is reusable."
cardforge lab promotion apply gravebound_test PROMO_0001
```

Applying a Prompt Lab promotion creates a new prompt-template version, appends the accepted guidance, records the lab evidence source, activates the new version, and stores an audit event.

## Image Lab promotion

Image Lab attempts can also become promotion requests, but automatic application is intentionally disabled. Image Lab evidence is visual and context-sensitive, so the app creates a reviewable guidance request rather than rewriting production prompts automatically.

```bash
cardforge lab image create gravebound_test CARD_0001
cardforge lab image run gravebound_test ILAB_0001 --prompt-append "violet rim light"
cardforge lab image review gravebound_test ILAB_0001 ATT_0001 LAB_CAND_001 --decision accepted --rating 5
cardforge lab image promote-request gravebound_test ILAB_0001 --notes "Violet rim light improved silhouette."
```

The request includes the attempt prompt, candidate manifest, operator review, and comparison score. A human can approve it as reusable guidance and then manually update the relevant art prompt or prompt template.

## A/B scoring

Prompt Lab runs now include a `score_100` metric based on parse success, number of card records, response size, and rules text compactness.

Image Lab attempts include a `score_100` metric based on candidate count, review coverage, best rating, and accepted candidates.

The scores are not final quality judgments. They are sorting aids for the operator and future dashboards.

## UI

The Labs page shows:

```text
Prompt Lab cases
Image Lab cases
Promotion requests
Prompt template versions
```

Promotion requests can be approved, rejected, and, for Prompt Lab promotions, applied directly from the UI.

## Safety rules

- Lab runs never directly mutate production artifacts.
- Prompt Lab promotions require an accepted run.
- Promotion requests require approval before application.
- Image Lab promotions cannot be auto-applied; they produce reviewable guidance only.
- Prompt template versions are stored as files and SQL rows for reproducibility.
