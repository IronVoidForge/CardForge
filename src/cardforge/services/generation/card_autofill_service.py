from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.cards.card_service import CardService
from cardforge.services.llm.llm_request_log import LLMRequestLog
from cardforge.services.llm.packet_parser import PacketRecord, parse_card_records
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService


class CardAutofillService:
    """Fill missing card fields through the same prompt/log/parse path used by live LLM calls."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.prompts = PromptTemplateService(self.db)
        self.llm_log = LLMRequestLog(self.db)

    def autofill_card(
        self,
        project_slug: str,
        card_key: str,
        *,
        use_mock: bool = True,
        force: bool = False,
        model: str | None = None,
    ) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            missing = self._missing_fields(card)
            if not force and not missing:
                return {"card_key": card_key, "changed": False, "missing_fields": [], "message": "No missing autofill fields."}
            prompt_package = self.prompts.render_package(
                project_slug,
                template_key="card_autofill_v1",
                task_type="card_autofill",
                set_id=card["set_id"],
                card_id=card["id"],
                conn=conn,
                context={
                    "project_slug": project_slug,
                    "card_key": card_key,
                    "name": card["name"],
                    "card_type": card["card_type"],
                    "rarity": card["rarity"],
                    "faction": card["faction"],
                    "missing_fields": missing,
                    "rules_text": card["rules_text"],
                    "flavor_text": card["flavor_text"],
                    "art_direction": card["art_direction"],
                },
            )
            request_id = self.llm_log.create(
                conn,
                project_id=project["id"],
                set_id=card["set_id"],
                card_id=card["id"],
                batch_id=None,
                project_slug=project_slug,
                task_type="card_autofill",
                model=model or ("mock-cardforge-autofill" if use_mock else self.db.settings.lmstudio_model),
                system_prompt=prompt_package.system_prompt,
                user_prompt=prompt_package.user_prompt,
                temperature=0.1,
                max_tokens=self.db.settings.lmstudio_max_tokens,
            )
            try:
                raw_response = self._autofill_response(card, missing=missing, use_mock=use_mock, prompt_package=prompt_package, model=model)
                records = parse_card_records(raw_response, expected_task="card_autofill")
                payload = self._record_payload(records[0])
                self.llm_log.complete(conn, request_id=request_id, project_slug=project_slug, raw_response=raw_response, parsed_payload=payload)
            except Exception as exc:
                self.llm_log.fail(conn, request_id=request_id, error=str(exc))
                raise
            updates = self._updates_from_payload(card, payload, only_missing=not force)
            if not updates:
                return {"card_key": card_key, "changed": False, "missing_fields": missing, "prompt_package_key": prompt_package.package_key, "message": "Autofill produced no applicable updates."}
            updated = self.cards.update_card_fields(
                project_slug,
                card_key,
                source="llm_mock_autofill" if use_mock else "llm_autofill",
                change_reason="Autofill missing card fields",
                conn=conn,
                **updates,
            )
            validation = self.cards.validator.validate(project_slug, updated).model_dump()
            report = {
                "card_key": card_key,
                "changed": True,
                "missing_fields": missing,
                "updated_fields": sorted(updates),
                "prompt_package_key": prompt_package.package_key,
                "prompt_package_path": prompt_package.package_markdown_path,
                "llm_request_id": request_id,
                "validation": validation,
            }
            self.asset_store.write_json(self.asset_store.project_root(project_slug) / "cards" / card_key / "autofill_report.json", report)
            return report

    def _missing_fields(self, card: Any) -> list[str]:
        missing: list[str] = []
        for field in ["type_line", "rules_text", "flavor_text", "design_notes", "art_direction", "template_id"]:
            if not str(card[field] or "").strip():
                missing.append(field)
        stats = json.loads(card["stats_json"] or "{}")
        if str(card["card_type"]).lower() in {"creature", "legendary"}:
            if stats.get("attack") is None:
                missing.append("attack")
            if stats.get("health") is None:
                missing.append("health")
        return missing

    def _autofill_response(self, card: Any, *, missing: list[str], use_mock: bool, prompt_package: Any, model: str | None) -> str:
        if not use_mock:
            result = LMStudioClient(self.db.settings).chat(
                system_prompt=prompt_package.system_prompt,
                user_prompt=prompt_package.user_prompt,
                model=model,
                temperature=0.1,
            )
            if not result.ok:
                raise RuntimeError(result.error or "LM Studio autofill call failed.")
            return result.text
        return self._mock_autofill_packet(card, missing)

    def _mock_autofill_packet(self, card: Any, missing: list[str]) -> str:
        card_type = str(card["card_type"] or "creature").lower()
        name = card["name"]
        template = str(card["template_id"] or f"default_{card_type}_front_v1")
        attack_health = ""
        stats = json.loads(card["stats_json"] or "{}")
        if card_type in {"creature", "legendary"}:
            cost = self._cost_value(card)
            attack = stats.get("attack") if stats.get("attack") is not None else max(1, cost - 1)
            health = stats.get("health") if stats.get("health") is not None else max(1, cost + 1)
            attack_health = f"attack: {attack}\nhealth: {health}\n"
        rules = str(card["rules_text"] or "").strip() or self._default_rules(card_type, name)
        flavor = str(card["flavor_text"] or "").strip() or "Even silence has a cost among the graves."
        art = str(card["art_direction"] or "").strip() or f"Dark fantasy card illustration of {name}, clear central silhouette, gothic lighting, no text, no border, no logo."
        design = str(card["design_notes"] or "").strip() or f"Autofilled {card_type} role for prototype testing; keep complexity low and template-friendly."
        type_line = str(card["type_line"] or "").strip() or card_type.title()
        return f"""[[CARDFORGE_PACKET]]
task: card_autofill
version: 1

[[CARDFORGE_RECORD]]
type: card
card_key: {card['card_key']}
type_line: {type_line}
keywords: {self._keywords_for(card_type)}
template_id: {template}
{attack_health}[[SECTION rules_text]]
{rules}
[[/SECTION]]
[[SECTION flavor_text]]
{flavor}
[[/SECTION]]
[[SECTION design_notes]]
{design}
[[/SECTION]]
[[SECTION art_direction]]
{art}
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]
"""

    def _record_payload(self, record: PacketRecord) -> dict[str, Any]:
        payload = dict(record.fields)
        payload.update(record.sections)
        return payload

    def _updates_from_payload(self, card: Any, payload: dict[str, Any], *, only_missing: bool) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        scalar_map = {
            "type_line": "type_line",
            "rules_text": "rules_text",
            "flavor_text": "flavor_text",
            "design_notes": "design_notes",
            "art_direction": "art_direction",
            "template_id": "template_id",
        }
        for key, db_key in scalar_map.items():
            value = str(payload.get(key) or "").strip()
            if not value:
                continue
            if only_missing and str(card[db_key] or "").strip():
                continue
            updates[db_key] = value
        keywords = self._split_list(payload.get("keywords"))
        if keywords:
            existing = json.loads(card["keywords_json"] or "[]")
            if not only_missing or not existing:
                updates["keywords_json"] = json.dumps(keywords)
        stats = json.loads(card["stats_json"] or "{}")
        changed_stats = False
        for key in ["attack", "health"]:
            value = self._int_or_none(payload.get(key))
            if value is None:
                continue
            if not only_missing or stats.get(key) is None:
                stats[key] = value
                changed_stats = True
        if changed_stats:
            updates["stats_json"] = json.dumps(stats)
        return updates

    def _default_rules(self, card_type: str, name: str) -> str:
        if card_type == "spell":
            return "Choose one: return a low-cost card from your discard pile to your hand, or curse an enemy."
        if card_type == "equipment":
            return "Equipped unit gets +1 attack. When it dies, create a 1/1 Bone Wisp."
        if card_type == "location":
            return "Once each turn, you may sacrifice a unit. If you do, draw a card then discard a card."
        return f"Guard. When {name} enters play, create a 1/1 Bone Wisp."

    def _keywords_for(self, card_type: str) -> str:
        return {
            "spell": "curse, graveyard",
            "equipment": "sacrifice",
            "location": "graveyard, sacrifice",
            "legendary": "summon, graveyard",
        }.get(card_type, "guard, summon")

    def _cost_value(self, card: Any) -> int:
        cost = json.loads(card["cost_json"] or "{}")
        return int(cost.get("generic") or 0)

    def _split_list(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip().lower().replace(" ", "_") for item in value if str(item).strip()]
        return [part.strip().lower().replace(" ", "_") for part in str(value).replace(";", ",").split(",") if part.strip()]

    def _int_or_none(self, value: Any) -> int | None:
        if value in {None, ""}:
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None
