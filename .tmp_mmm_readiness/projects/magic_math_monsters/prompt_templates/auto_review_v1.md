# Title
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
