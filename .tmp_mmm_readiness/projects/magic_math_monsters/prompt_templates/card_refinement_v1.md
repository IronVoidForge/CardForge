# Title
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
