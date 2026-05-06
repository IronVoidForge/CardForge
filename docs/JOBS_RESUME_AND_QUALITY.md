# Jobs, Resume, and Quality Gates

CardForge now has a local offline-safe job queue so long-running work can be queued, retried, audited, and eventually moved behind live LM Studio/ComfyUI adapters without changing the UI workflow.

## Job queue

Jobs are stored in `generation_jobs` and use deterministic services by default.

Supported offline job types:

- `batch_generate`
- `batch_validate`
- `batch_auto_review`
- `card_autofill`
- `card_refine`
- `card_auto_review`
- `art_generate_dummy`
- `art_auto_review`
- `render_card`
- `export_json`
- `export_csv`
- `export_markdown`
- `export_png`

CLI examples:

```bash
cardforge job enqueue-batch-generate gravebound_test SET001 --count 12 --request "Generate gothic necromancer cards."
cardforge job run-next gravebound_test
cardforge job run-all gravebound_test
cardforge job list gravebound_test
cardforge job retry gravebound_test 1
```

The web UI exposes the same queue at:

```text
/projects/<project_slug>/jobs
```

## Resume planner

The resume planner is read-only. It recommends the next safe action and can optionally queue one suggested job.

```bash
cardforge resume plan gravebound_test
cardforge resume enqueue-next gravebound_test
```

The planner currently checks for:

- missing set
- no cards
- pending/running jobs
- auto-review rework blockers
- open review items
- missing locked art
- missing renders
- missing exports

## Observability

The queue writes append-only audit events for:

- job enqueue
- job start
- job completion
- job failure
- job retry

Diagnostics:

```bash
cardforge doctor check
```

Web health endpoint:

```text
/healthz
```

The health endpoint verifies local workspace writability, database migration/open, and integration configuration presence. It does not require live LM Studio or ComfyUI.

## Quality gates

Local quality check:

```bash
make quality
```

Equivalent explicit command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python scripts/quality_check.py
```

CI runs the strict version after installing dev dependencies:

```bash
python scripts/quality_check.py --strict
```

Current gates:

- repository text-format checks for trailing whitespace, tab characters, and missing final newline
- bytecode compile pass
- Ruff critical lint checks when installed
- pytest suite

`ruff` is optional locally but required in CI.
