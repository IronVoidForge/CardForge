from __future__ import annotations

import json
from sqlite3 import Row

from cardforge.files.asset_store import AssetStore
from cardforge.schemas.card import CardValidationReport, ValidationIssue


class CardValidationService:
    def __init__(self, asset_store: AssetStore | None = None) -> None:
        self.asset_store = asset_store or AssetStore()

    def validate(self, project_slug: str, card: Row) -> CardValidationReport:
        issues: list[ValidationIssue] = []
        registry = self._load_json(project_slug, "card_type_registry.json", default={"types": {}})
        keyword_registry = self._load_json(project_slug, "keyword_registry.json", default={"keywords": {}})
        template_registry = self._load_json(project_slug, "template_registry.json", default={"templates": {}})
        card_type = str(card["card_type"] or "").strip().lower()
        type_def = registry.get("types", {}).get(card_type)
        if not type_def:
            issues.append(ValidationIssue(code="unknown_card_type", severity="error", field="card_type", message=f"Unknown card type: {card_type}"))
            return CardValidationReport(card_key=card["card_key"], valid=False, issues=issues)

        required = set(type_def.get("required_fields", []))
        if "name" in required and not str(card["name"] or "").strip():
            issues.append(ValidationIssue(code="missing_name", severity="error", field="name", message="Name is required."))
        if "rules_text" in required and not str(card["rules_text"] or "").strip():
            issues.append(ValidationIssue(code="missing_rules_text", severity="error", field="rules_text", message="Rules text is required."))
        if "type_line" in required and not str(card["type_line"] or "").strip():
            issues.append(ValidationIssue(code="missing_type_line", severity="error", field="type_line", message="Type line is required."))

        stats = json.loads(card["stats_json"] or "{}")
        allows_stats = bool(type_def.get("allows_stats"))
        has_stats = stats.get("attack") is not None or stats.get("health") is not None
        if not allows_stats and has_stats:
            issues.append(ValidationIssue(code="stats_not_allowed", severity="error", field="stats", message=f"{card_type} cards should not have attack/health stats."))
        if allows_stats:
            if "attack" in required and stats.get("attack") is None:
                issues.append(ValidationIssue(code="missing_attack", severity="error", field="stats.attack", message="Attack is required."))
            if "health" in required and stats.get("health") is None:
                issues.append(ValidationIssue(code="missing_health", severity="error", field="stats.health", message="Health is required."))

        cost = json.loads(card["cost_json"] or "{}")
        if "cost" in required and int(cost.get("generic") or 0) < 0:
            issues.append(ValidationIssue(code="invalid_cost", severity="error", field="cost", message="Cost must not be negative."))

        if len(str(card["name"] or "")) > 34:
            issues.append(ValidationIssue(code="name_too_long", severity="warning", field="name", message="Name may overflow the title box."))
        if len(str(card["type_line"] or "")) > 54:
            issues.append(ValidationIssue(code="type_line_too_long", severity="warning", field="type_line", message="Type line may overflow the type box."))
        if len(str(card["rules_text"] or "")) > 420:
            issues.append(ValidationIssue(code="rules_text_too_long", severity="warning", field="rules_text", message="Rules text may overflow the rules box."))

        template_id = str(card["template_id"] or "").strip()
        if not template_id:
            issues.append(ValidationIssue(code="missing_template", severity="error", field="template_id", message="Template ID is required."))
        elif template_id not in template_registry.get("templates", {}):
            issues.append(ValidationIssue(code="unknown_template", severity="error", field="template_id", message=f"Template is not registered: {template_id}"))

        keywords = json.loads(card["keywords_json"] or "[]")
        known_keywords = set(keyword_registry.get("keywords", {}))
        for keyword in keywords:
            normalized = str(keyword or "").strip().lower()
            if normalized and normalized not in known_keywords:
                issues.append(ValidationIssue(code="unknown_keyword", severity="warning", field="keywords", message=f"Keyword is not registered: {normalized}"))

        valid = not any(issue.severity == "error" for issue in issues)
        return CardValidationReport(card_key=card["card_key"], valid=valid, issues=issues)

    def _load_json(self, project_slug: str, filename: str, *, default: dict) -> dict:
        path = self.asset_store.project_root(project_slug) / filename
        if not path.exists():
            return default
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
        return payload if isinstance(payload, dict) else default
