from __future__ import annotations

PROJECT_DIRS = [
    "briefs",
    "batches",
    "cards",
    "templates/fronts",
    "templates/backs",
    "templates/frames",
    "templates/symbols",
    "prompt_templates",
    "prompt_packages",
    "auto_reviews",
    "exports/png",
    "exports/pdf",
    "exports/json",
    "exports/csv",
    "logs/llm",
    "logs/comfy",
    "logs/render",
    "logs/review",
]

DEFAULT_CARD_TYPE_REGISTRY = {
    "schema_version": "2026-05-card-type-registry-v1",
    "types": {
        "creature": {
            "display_name": "Creature",
            "required_fields": ["name", "cost", "type_line", "rules_text", "attack", "health", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "subtypes", "faction"],
            "template_id": "default_creature_front_v1",
            "allows_stats": True,
        },
        "spell": {
            "display_name": "Spell",
            "required_fields": ["name", "cost", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_spell_front_v1",
            "allows_stats": False,
        },
        "equipment": {
            "display_name": "Equipment",
            "required_fields": ["name", "cost", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_equipment_front_v1",
            "allows_stats": False,
        },
        "location": {
            "display_name": "Location",
            "required_fields": ["name", "type_line", "rules_text", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "faction"],
            "template_id": "default_location_front_v1",
            "allows_stats": False,
        },
        "legendary": {
            "display_name": "Legendary",
            "required_fields": ["name", "cost", "type_line", "rules_text", "attack", "health", "rarity"],
            "optional_fields": ["keywords", "flavor_text", "subtypes", "faction"],
            "template_id": "default_legendary_front_v1",
            "allows_stats": True,
        },
    },
}

DEFAULT_KEYWORD_REGISTRY = {
    "schema_version": "2026-05-keyword-registry-v1",
    "keywords": {
        "guard": {"display_name": "Guard", "rules_text": "This can block attacks against nearby allies."},
        "summon": {"display_name": "Summon", "rules_text": "Creates another unit or token."},
        "curse": {"display_name": "Curse", "rules_text": "Applies a negative ongoing effect."},
        "sacrifice": {"display_name": "Sacrifice", "rules_text": "Destroy or spend one of your own cards for value."},
        "graveyard": {"display_name": "Graveyard", "rules_text": "Interacts with discarded or destroyed cards."},
    },
}


DEFAULT_PROMPT_FORMAT_MARKDOWN = """# CardForge Prompt Format

CardForge model prompts use a prompt package plus a strict packet output contract. The package is markdown for humans and logs. The model response should be one tagged packet for machines.

## Required response envelope

```text
[[CARDFORGE_PACKET]]
task: <task_name>
version: 1

[[CARDFORGE_RECORD]]
type: card
name: Example Card
card_type: creature
rarity: common
cost: 2
[[SECTION rules_text]]
Concise rules text.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]
```

## Parser fallback policy

1. Tagged CardForge packet.
2. JSON object/list salvage.
3. Markdown table salvage.
4. Markdown heading-block salvage.
5. Schema coercion and deterministic validation.
"""

DEFAULT_PROMPT_TEMPLATES = {
    "card_batch_generation_v1": """# Title
Card Batch Generation v1

# ID
card_batch_generation_v1

# Task
card_batch

# Model Role
You are CardForge's local card design model. Return one CARDFORGE packet only. Do not generate final card images. Keep all card text concise enough for a physical card template.

# Inputs
- project_slug: {project_slug}
- set_code: {set_code}
- set_name: {set_name}
- requested_count: {count}
- user_request: {request_text}

# Instructions
Generate exactly {count} prototype cards that fit the user's request. Use a balanced mix of card types unless the request says otherwise. Each card needs enough structure for validation, rendering, art prompting, and later review. Do not put card frames, logos, or readable text into art directions.

# Output Contract
Each record must include name, card_type, rarity, faction, cost, template_id, and sections for rules_text, design_notes, and art_direction. Creature and legendary records should include attack and health.

# Packet Shape
[[CARDFORGE_PACKET]]
task: card_batch
version: 1

[[CARDFORGE_RECORD]]
type: card
name: Example Card
card_type: creature
rarity: common
faction: Example
cost: 2
attack: 1
health: 3
keywords: guard, sacrifice
template_id: default_creature_front_v1
back_template_id: default_card_back_v1
[[SECTION rules_text]]
Concise rules text.
[[/SECTION]]
[[SECTION design_notes]]
Design role and balance note.
[[/SECTION]]
[[SECTION art_direction]]
Illustration-only art direction. No text, no border, no logo.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]

# Sources
- set brief
- card type registry
- keyword registry
""",
    "card_autofill_v1": """# Title
Card Autofill v1

# ID
card_autofill_v1

# Task
card_autofill

# Model Role
You complete missing card fields without changing the card's identity. Return one CARDFORGE packet only.

# Inputs
- project_slug: {project_slug}
- card_key: {card_key}
- name: {name}
- card_type: {card_type}
- rarity: {rarity}
- faction: {faction}
- missing_fields: {missing_fields}
- current_rules_text: {rules_text}
- current_flavor_text: {flavor_text}
- current_art_direction: {art_direction}

# Instructions
Fill only missing or weak fields. Keep rules text concise. Preserve card name, type, rarity, and faction unless a field is explicitly missing. Use registered keywords when useful.

# Output Contract
Return a single card record with any repaired scalar fields plus rules_text, flavor_text, design_notes, and art_direction sections when useful.

# Packet Shape
[[CARDFORGE_PACKET]]
task: card_autofill
version: 1

[[CARDFORGE_RECORD]]
type: card
card_key: {card_key}
type_line: Creature — Example
keywords: guard
template_id: default_creature_front_v1
[[SECTION rules_text]]
Concise completed rules text.
[[/SECTION]]
[[SECTION flavor_text]]
Optional flavor text.
[[/SECTION]]
[[SECTION design_notes]]
Role and balance note.
[[/SECTION]]
[[SECTION art_direction]]
Illustration-only prompt.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]

# Sources
- card.json
- validation report
""",
    "card_refinement_v1": """# Title
Card Refinement v1

# ID
card_refinement_v1

# Task
card_refinement

# Model Role
You revise a card according to validation and auto-review findings. Return one CARDFORGE packet only.

# Inputs
- project_slug: {project_slug}
- card_key: {card_key}
- name: {name}
- card_type: {card_type}
- findings: {findings}
- recommendations: {recommendations}
- current_rules_text: {rules_text}

# Instructions
Address the recommendations while preserving the card's concept. Shorten overlong text. Clarify ambiguous rules. Fill art direction if missing.

# Output Contract
Return exactly one card record with only improved fields and markdown sections that should replace current card text.

# Packet Shape
[[CARDFORGE_PACKET]]
task: card_refinement
version: 1

[[CARDFORGE_RECORD]]
type: card
card_key: {card_key}
[[SECTION rules_text]]
Revised concise rules text.
[[/SECTION]]
[[SECTION design_notes]]
What changed and why.
[[/SECTION]]
[[SECTION art_direction]]
Updated art direction if needed.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]

# Sources
- validation report
- auto review report
""",
    "auto_review_v1": """# Title
Card Auto Review v1

# ID
auto_review_v1

# Task
card_auto_review

# Model Role
You review card text like a strict production assistant. Return one packet or concise JSON findings.

# Inputs
- project_slug: {project_slug}
- card_key: {card_key}
- name: {name}
- card_type: {card_type}
- rules_text: {rules_text}
- validation_summary: {validation_summary}

# Instructions
Score the card for template fit, clarity, required fields, and readiness for art/rendering. Recommend rework only when useful.

# Output Contract
Return status, score_100, findings, and recommendations.

# Packet Shape
[[CARDFORGE_PACKET]]
task: card_auto_review
version: 1
status: needs_human_review
score_100: 75
[[SECTION findings]]
- issue
[[/SECTION]]
[[SECTION recommendations]]
- recommendation
[[/SECTION]]
[[/CARDFORGE_PACKET]]

# Sources
- card.json
- validation report
""",
}

DEFAULT_TEMPLATE_REGISTRY = {
    "schema_version": "2026-05-template-registry-v1",
    "templates": {
        "default_creature_front_v1": {"template_type": "front", "card_type": "creature"},
        "default_spell_front_v1": {"template_type": "front", "card_type": "spell"},
        "default_equipment_front_v1": {"template_type": "front", "card_type": "equipment"},
        "default_location_front_v1": {"template_type": "front", "card_type": "location"},
        "default_legendary_front_v1": {"template_type": "front", "card_type": "legendary"},
        "default_card_back_v1": {"template_type": "back", "card_type": "any"},
    },
}
