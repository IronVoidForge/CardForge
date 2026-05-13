# CardForge UI QA Report

Date: 2026-05-12
Target: http://127.0.0.1:8765
Mode: report-only browser QA
Live generation constraint: did not run LM Studio or ComfyUI generation/health actions

## Summary

Health score: 82/100

The implemented UI is a solid local-first operator slice. I verified project creation, set creation, manual card creation, placeholder rendering, review queue decisions, empty job handling, lab case creation, prompt studio browsing, template preview rendering, integration settings display, JSON export, and the mobile operator dashboard/review route.

No browser console errors were observed. The only repeated console warning was Chromium's deprecation warning for `apple-mobile-web-app-capable` without `mobile-web-app-capable`.

## Implemented Surface Observed

- Desktop project dashboard with create/list projects.
- Project dashboard with stats, set creation, labs, prompt studio, templates, integrations, reviews, and jobs navigation.
- Set detail with simulated batch form, manual card form, card list, exports.
- Card detail with editable text fields, version history, offline helpers, placeholder render, art candidate controls, and review items.
- Review queue with approve/rework/reject/defer forms.
- Jobs page with empty queue handling and resume planner copy.
- Labs page with Prompt Lab and Image Lab case creation plus version/promotion tables.
- Prompt Studio with active template versions and version detail/diff views.
- Template library/detail with JSON editor and render-preview action.
- Integration settings for LM Studio and ComfyUI, including saved config display and workflow registry.
- Mobile dashboard, mobile review queue, mobile review detail, bottom nav, lock button, and rendered card preview.

## Findings

### High: Mobile quick failure tag submits the review decision

Repro:
1. Open `http://127.0.0.1:8765/m/qa_manual_test/review/4`.
2. Leave the decision dropdown at its default value, `Request rework`.
3. Tap the quick tag `good candidate`.

Observed: the app navigated to `/m/qa_manual_test/review/3`, and the open review count dropped from 3 to 2. This indicates the tag button submitted the decision form rather than only filling/appending a tag.

Expected: quick tag buttons should update the tags field only, or require an explicit `Submit with notes` tap.

Evidence: `cardforge-mobile-review-overlap.png`

### Medium: Mobile review detail count reads as item id, not queue position

Repro:
1. From the mobile dashboard, tap `Review next item`.

Observed: header text said `Review item 4 of 3 open`, which is impossible as a position count.

Expected: either `Review item 1 of 3 open` or `Review #4 · 3 open`.

### Medium: Integrations page horizontally overflows on desktop-width viewport

Repro:
1. Open `http://127.0.0.1:8765/projects/qa_manual_test/integrations`.
2. Use a roughly 1024px wide viewport.

Observed: the page content measured wider than the viewport, with long config paths and two-column forms pushing the main region horizontally.

Expected: config path and integration cards should wrap or stack before causing horizontal overflow.

### Medium: Export actions provide no visible success feedback

Repro:
1. Open the set page.
2. Click `JSON`.

Observed: the export artifact was written under `workspace/projects/qa_manual_test/exports/json`, but the page stayed visually unchanged with no toast, path, link, timestamp, or success state.

Expected: show the created export path and a success/failure message.

### Low: PWA meta warning repeats on every page

Observed: Chromium repeatedly warned that `<meta name="apple-mobile-web-app-capable" content="yes">` is deprecated and recommends including `mobile-web-app-capable`.

Expected: include the modern meta tag to keep console health clean.

### Low: Prompt version detail says protected, but shows editable text area

Repro:
1. Open an active prompt version detail page.

Observed: evidence summary says active versions are protected, but the markdown appears in a normal textarea. There is no save button, so the data is probably safe, but the control visually implies editing may be possible.

Expected: render protected active versions in a read-only field or static code block.

## Not Tested By Request

- LM Studio health/test link.
- ComfyUI health/test link.
- Prepare Comfy workflow submit.
- Actual live text/image generation.

## Artifacts

- `cardforge-projects-empty.png`
- `cardforge-card-rendered.png`
- `cardforge-mobile-review-overlap.png`

