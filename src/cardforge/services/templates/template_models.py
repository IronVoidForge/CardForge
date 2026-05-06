from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TemplateBox:
    """Integer pixel box in left/top/right/bottom coordinates."""

    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def from_value(cls, value: Any) -> "TemplateBox":
        if isinstance(value, dict):
            if {"x", "y", "w", "h"}.issubset(value):
                x = int(value["x"])
                y = int(value["y"])
                return cls(x, y, x + int(value["w"]), y + int(value["h"]))
            if {"left", "top", "right", "bottom"}.issubset(value):
                return cls(int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))
        if isinstance(value, (list, tuple)) and len(value) == 4:
            return cls(int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        raise ValueError(f"Invalid template box: {value!r}")

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


def layer_by_id(template: dict[str, Any], layer_id: str) -> dict[str, Any]:
    for layer in template.get("layers", []):
        if isinstance(layer, dict) and str(layer.get("id", "")).strip() == layer_id:
            return layer
    return {}


def box_for_layer(template: dict[str, Any], layer_id: str, fallback: tuple[int, int, int, int]) -> TemplateBox:
    layer = layer_by_id(template, layer_id)
    if not layer:
        return TemplateBox.from_value(fallback)
    try:
        return TemplateBox.from_value(layer.get("box", fallback))
    except ValueError:
        return TemplateBox.from_value(fallback)


def rgb(value: Any, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
            except ValueError:
                return fallback
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback
