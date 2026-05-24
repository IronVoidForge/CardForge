# Title
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
