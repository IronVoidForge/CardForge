from __future__ import annotations

from copy import deepcopy
from typing import Any


FRONT_TEMPLATE_BASE: dict[str, Any] = {
    "template_type": "front",
    "canvas": {"width": 750, "height": 1050, "bleed": 24, "safe_margin": 52},
    "colors": {
        "background": [236, 232, 220],
        "border": [32, 28, 35],
        "frame": [70, 60, 82],
        "panel": [245, 241, 229],
        "text": [25, 20, 20],
        "muted_text": [55, 45, 55],
        "art_placeholder": [135, 125, 145],
    },
    "font_roles": {
        "title": {"size": 40, "min_size": 24},
        "cost": {"size": 30, "min_size": 20},
        "type_line": {"size": 28, "min_size": 18},
        "rules": {"size": 27, "min_size": 17},
        "flavor": {"size": 21, "min_size": 15},
        "stats": {"size": 32, "min_size": 20},
    },
    "layers": [
        {"id": "outer_frame", "type": "rounded_rect", "box": [24, 24, 726, 1026], "radius": 34},
        {"id": "inner_frame", "type": "rounded_rect", "box": [46, 46, 704, 1004], "radius": 24},
        {"id": "title", "type": "text", "source": "card.name", "box": [86, 82, 610, 142], "max_lines": 1},
        {"id": "cost", "type": "cost", "source": "card.cost", "box": [625, 78, 690, 143], "max_lines": 1},
        {"id": "title_bar", "type": "rounded_rect", "box": [64, 64, 686, 150], "radius": 14},
        {"id": "art", "type": "image_slot", "source": "locked_art", "box": [78, 170, 672, 520], "fit": "cover"},
        {"id": "type_line", "type": "text", "source": "card.type_line", "box": [96, 542, 650, 586], "max_lines": 1},
        {"id": "type_bar", "type": "rounded_rect", "box": [78, 535, 672, 590], "radius": 8},
        {"id": "rules_panel", "type": "rounded_rect", "box": [78, 605, 672, 890], "radius": 10},
        {"id": "rules_text", "type": "rich_text", "source": "card.rules_text", "box": [92, 620, 658, 865], "max_lines": 12},
        {"id": "flavor_text", "type": "rich_text", "source": "card.flavor_text", "box": [94, 905, 634, 980], "max_lines": 3},
        {"id": "stats", "type": "stats", "source": "card.stats", "box": [560, 930, 680, 995]},
    ],
}

BACK_TEMPLATE: dict[str, Any] = {
    "template_type": "back",
    "card_type": "any",
    "canvas": {"width": 750, "height": 1050, "bleed": 24, "safe_margin": 52},
    "colors": {
        "background": [40, 33, 52],
        "border": [210, 185, 110],
        "secondary": [120, 83, 185],
        "text": [230, 215, 160],
    },
    "font_roles": {"title": {"size": 58, "min_size": 36}, "subtitle": {"size": 24, "min_size": 18}},
    "layers": [
        {"id": "outer_frame", "type": "rounded_rect", "box": [40, 40, 710, 1010], "radius": 42},
        {"id": "inner_frame", "type": "rounded_rect", "box": [74, 74, 676, 976], "radius": 30},
        {"id": "emblem", "type": "ellipse", "box": [190, 310, 560, 680]},
        {"id": "title", "type": "text", "source": "project.name", "box": [80, 700, 670, 800], "max_lines": 1},
        {"id": "subtitle", "type": "text", "source": "static.prototype", "box": [80, 800, 670, 850], "max_lines": 1},
    ],
}

CARD_TYPE_VARIANTS = {
    "creature": {"accent": [70, 60, 82], "panel": [245, 241, 229]},
    "spell": {"accent": [45, 64, 106], "panel": [236, 242, 249]},
    "equipment": {"accent": [94, 72, 38], "panel": [246, 238, 219]},
    "location": {"accent": [49, 91, 67], "panel": [230, 242, 228]},
    "legendary": {"accent": [112, 70, 133], "panel": [247, 236, 250]},
}


def default_front_template(template_key: str, card_type: str) -> dict[str, Any]:
    template = deepcopy(FRONT_TEMPLATE_BASE)
    variant = CARD_TYPE_VARIANTS.get(card_type, CARD_TYPE_VARIANTS["creature"])
    template["template_key"] = template_key
    template["name"] = f"Default {card_type.title()} Front"
    template["card_type"] = card_type
    template["colors"]["frame"] = variant["accent"]
    template["colors"]["panel"] = variant["panel"]
    return template


def default_back_template() -> dict[str, Any]:
    template = deepcopy(BACK_TEMPLATE)
    template["template_key"] = "default_card_back_v1"
    template["name"] = "Default Card Back"
    return template


def default_template_registry() -> dict[str, Any]:
    templates: dict[str, Any] = {}
    for card_type in ["creature", "spell", "equipment", "location", "legendary"]:
        key = f"default_{card_type}_front_v1"
        templates[key] = default_front_template(key, card_type)
    templates["default_card_back_v1"] = default_back_template()
    return {"schema_version": "2026-05-template-registry-v2", "templates": templates}


DEFAULT_TEMPLATE_REGISTRY = default_template_registry()
