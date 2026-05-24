# CardForge Prompt Format

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
