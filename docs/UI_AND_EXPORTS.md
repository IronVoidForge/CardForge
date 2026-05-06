# CardForge UI and export workflow

This pass adds the first local operator UI and offline export workflow.

## Local UI

Start the UI with:

```bash
cardforge ui serve --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

The UI is intentionally local-first and offline-safe. It works with simulated batch generation, dummy art, deterministic auto-review, deterministic rendering, and project-file serving. It does not require LM Studio or ComfyUI to be running.

## UI surfaces

Implemented pages:

```text
/                                      Project home and project creation
/projects/{project_slug}               Project dashboard
/projects/{project_slug}/sets/{set}    Set detail, generation, manual cards, exports
/projects/{project_slug}/batches/{id}  Batch detail and batch validation/auto-review
/projects/{project_slug}/cards/{id}    Card editor, preview, art candidates, render actions
/projects/{project_slug}/review        Review queue with approve/reject/rework/defer actions
/assets/{workspace_path}               Safe workspace asset serving
```

## UI actions

The UI can currently perform the offline-safe operator loop:

```text
Create project
Create set
Generate simulated 10-15 card batch
Create manual card
Validate batch/card
Auto-review batch/card
Autofill missing card fields
Refine card text/art direction
Generate dummy art candidates
Auto-review art candidate
Approve/reject/lock art candidate
Render with placeholder or locked art
Review queue decisions
Export JSON/CSV/Markdown/PNG
```

## Export formats

Implemented export commands:

```bash
cardforge export json gravebound_test SET001
cardforge export csv gravebound_test SET001
cardforge export markdown gravebound_test SET001
cardforge export png gravebound_test SET001
```

Export outputs land under:

```text
projects/<project_slug>/exports/json/
projects/<project_slug>/exports/csv/
projects/<project_slug>/exports/markdown/
projects/<project_slug>/exports/png/<set_code>/
```

PNG export copies the latest rendered front/back/preview images for cards that have render records and writes an `EXPORT_MANIFEST.json` with any missing renders.

## Testing notes

The automated UI tests use FastAPI's `TestClient`, simulated generation, dummy art, locked-art rendering, JSON export, and review queue pages. Real LM Studio and ComfyUI remain manual integration points and are not required for automated tests.
