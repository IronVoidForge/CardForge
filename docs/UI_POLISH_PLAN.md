# CardForge UI Polish Plan

CardForge should feel like a calm production console: clear next action, visible state, reversible confidence, and no mystery after an operation.

## Product Shape

- Make the project dashboard the operator's home base: what exists, what needs attention, and what to do next.
- Keep generation, review, render, export, labs, and integrations visually distinct so users never wonder whether they are editing data, running offline simulation, or touching live tools.
- Treat mobile as the review cockpit: big previews, thumb-friendly decisions, explicit submit moments, and no accidental state changes.
- Treat desktop as the workshop: denser tables, stronger file/path feedback, and edit forms with clear save states.

## Design Principles

- Every mutating action should return with visible confirmation, including export path, render id, or review decision result.
- Buttons that submit decisions should look and read like decisions. Smaller cue/tag controls should only fill fields.
- Protected records should look read-only. Proposed records should look editable.
- Long technical values should wrap inside their panel. No page should require horizontal scrolling except data tables.
- Use calm density over marketing drama: stable panels, compact headings, clear labels, and predictable navigation.

## Near-Term UI Work

- Add success callouts for render, lab case creation, integration saves, template preview, and review decisions.
- Add route-level empty/error states that explain what to do next without sounding like documentation.
- Normalize button hierarchy: primary for the expected next action, secondary for safe alternatives, danger only for destructive rejection.
- Add small "live service" badges on LM Studio/Comfy health links so users know those actions may contact external local services.
- Add a review-focused mobile layout pass for 375px, 430px, tablet portrait, and desktop.

## Longer-Term UI Work

- Add a compact activity rail for recent exports, renders, review decisions, and lab artifacts.
- Add per-page breadcrumb context for project > set > card without increasing visual noise.
- Add keyboard-friendly desktop review controls.
- Add a visual card/render comparison mode for before/after template edits.
- Add inline validation summaries after saves instead of only redirecting.
