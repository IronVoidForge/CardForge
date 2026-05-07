# Mobile Review Flow and Prompt Template Studio

This phase adds two production-operator improvements:

1. A focused mobile review flow for phone/tablet sessions.
2. A Prompt Template Studio for safe prompt-template version editing, review, and activation.

## Mobile review flow

The mobile UI remains a browser/PWA surface served by the workstation:

```bash
cardforge ui serve --mode both --host 0.0.0.0 --port 8765 --password "local-password"
```

Open the phone/tablet view at:

```text
http://<workstation-ip>:8765/m
```

The improved review flow is:

```text
Mobile dashboard -> Review next item -> Focused review page -> approve/rework/reject/defer -> next item
```

Routes:

```text
/m/<project_slug>/review
/m/<project_slug>/review/next
/m/<project_slug>/review/<review_id>
```

The focused page includes:

- large preview image with tap-to-zoom link
- review metadata details
- one-tap approve/rework/reject/defer buttons
- voice-dictation-friendly note form
- quick failure tags based on review type
- decision history
- next/previous review navigation

The generic review decision endpoint now accepts:

```text
return_to
reason
notes
tags
```

This keeps mobile and desktop actions routed through the same review service.

## Prompt Template Studio

Prompt template edits are now versioned and reviewable. The studio never edits the active production markdown directly unless a version is explicitly activated.

Routes:

```text
/projects/<project_slug>/prompt-studio
/projects/<project_slug>/prompt-studio/<version_key>
```

Supported workflow:

```text
Sync versions
Create editable proposal from active template
Edit proposed markdown
Validate required sections
Review unified diff against active
Approve proposed version
Activate approved version
```

Required prompt markdown sections remain:

```text
# Title
# Task
# Model Role
# Instructions
```

The version detail page shows:

- selected version metadata
- active version metadata
- unified diff
- related lab promotion requests
- evidence summaries when available
- protected read-only view for active/superseded/rejected versions
- editable textarea for proposed/approved versions

## Safety model

- Active versions cannot be edited in place.
- Rejected and superseded versions are read-only.
- Approved versions can still be edited, but saving resets them to proposed.
- Activation requires an approved version.
- Validation runs before a proposed markdown file is saved.

## Tests

Relevant tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider \
  tests/test_mobile_ui.py \
  tests/test_prompt_template_studio.py
```
