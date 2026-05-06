from __future__ import annotations

import json
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.services.cards.card_service import CardService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.llm.llm_request_log import LLMRequestLog
from cardforge.services.llm.packet_parser import PacketRecord, parse_card_records
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.review.auto_review_service import AutoReviewService


class CardRefinementService:
    """Autofill + auto-review + model-shaped refinement loop.

    Works fully offline by using deterministic packet output. The live path is
    intentionally behind the same prompt package and parser boundary.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.prompts = PromptTemplateService(self.db)
        self.llm_log = LLMRequestLog(self.db)
        self.autofill = CardAutofillService(self.db)
        self.auto_review = AutoReviewService(self.db)

    def refine_card(
        self,
        project_slug: str,
        card_key: str,
        *,
        use_mock: bool = True,
        autofill_first: bool = True,
        model: str | None = None,
    ) -> dict[str, Any]:
        autofill_report: dict[str, Any] | None = None
        if autofill_first:
            autofill_report = self.autofill.autofill_card(project_slug, card_key, use_mock=use_mock, force=False, model=model)
        before_review = self.auto_review.review_card_text(project_slug, card_key, use_mock=use_mock)
        if before_review["auto_status"] == "strong_pass":
            return {
                "card_key": card_key,
                "changed": bool(autofill_report and autofill_report.get("changed")),
                "autofill": autofill_report,
                "before_review": before_review,
                "after_review": before_review,
                "message": "Auto-review passed; no refinement needed.",
            }
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            prompt_package = self.prompts.render_package(
                project_slug,
                template_key="card_refinement_v1",
                task_type="card_refinement",
                set_id=card["set_id"],
                card_id=card["id"],
                conn=conn,
                context={
                    "project_slug": project_slug,
                    "card_key": card_key,
                    "name": card["name"],
                    "card_type": card["card_type"],
                    "rules_text": card["rules_text"],
                    "findings": before_review.get("findings", []),
                    "recommendations": before_review.get("recommendations", []),
                },
            )
            request_id = self.llm_log.create(
                conn,
                project_id=project["id"],
                set_id=card["set_id"],
                card_id=card["id"],
                batch_id=None,
                project_slug=project_slug,
                task_type="card_refinement",
                model=model or ("mock-cardforge-refinement" if use_mock else self.db.settings.lmstudio_model),
                system_prompt=prompt_package.system_prompt,
                user_prompt=prompt_package.user_prompt,
                temperature=0.1,
                max_tokens=self.db.settings.lmstudio_max_tokens,
            )
            try:
                raw_response = self._refinement_response(card, before_review=before_review, use_mock=use_mock, prompt_package=prompt_package, model=model)
                records = parse_card_records(raw_response, expected_task="card_refinement")
                payload = self._record_payload(records[0])
                self.llm_log.complete(conn, request_id=request_id, project_slug=project_slug, raw_response=raw_response, parsed_payload=payload)
            except Exception as exc:
                self.llm_log.fail(conn, request_id=request_id, error=str(exc))
                raise
            updates = self._updates_from_payload(card, payload)
            if updates:
                self.cards.update_card_fields(
                    project_slug,
                    card_key,
                    source="llm_mock_refinement" if use_mock else "llm_refinement",
                    change_reason="Auto refinement from review findings",
                    conn=conn,
                    **updates,
                )
        after_review = self.auto_review.review_card_text(project_slug, card_key, use_mock=use_mock)
        result = {
            "card_key": card_key,
            "changed": bool(updates),
            "updated_fields": sorted(updates),
            "autofill": autofill_report,
            "before_review": before_review,
            "after_review": after_review,
            "llm_request_id": request_id,
            "prompt_package_key": prompt_package.package_key,
            "prompt_package_path": prompt_package.package_markdown_path,
        }
        self.asset_store.write_json(self.asset_store.project_root(project_slug) / "cards" / card_key / "refinement_report.json", result)
        return result

    def _refinement_response(self, card: Any, *, before_review: dict[str, Any], use_mock: bool, prompt_package: Any, model: str | None) -> str:
        if not use_mock:
            result = LMStudioClient(self.db.settings).chat(
                system_prompt=prompt_package.system_prompt,
                user_prompt=prompt_package.user_prompt,
                model=model,
                temperature=0.1,
            )
            if not result.ok:
                raise RuntimeError(result.error or "LM Studio refinement call failed.")
            return result.text
        rules = self._refined_rules(card, before_review)
        design = "Auto-refined from validation and review findings. Preserved card concept while improving template fit and clarity."
        art = str(card["art_direction"] or "").strip() or f"Fantasy trading card illustration of {card['name']}, clear central subject, no text, no border, no logo."
        return f"""[[CARDFORGE_PACKET]]
task: card_refinement
version: 1

[[CARDFORGE_RECORD]]
type: card
card_key: {card['card_key']}
[[SECTION rules_text]]
{rules}
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

    def _refined_rules(self, card: Any, review: dict[str, Any]) -> str:
        text = " ".join(str(card["rules_text"] or "").split())
        if not text:
            return f"When {card['name']} enters play, gain 1 resource."
        text = text.replace("thing", "card").replace("stuff", "cards")
        text = text.replace("any card", "a card in a discard pile")
        if len(text) > 280:
            sentences = [part.strip() for part in text.replace("!", ".").split(".") if part.strip()]
            text = ". ".join(sentences[:2]).strip()
        if not text.endswith((".", "!", ")")):
            text += "."
        if review.get("auto_status") == "needs_rework" and len(text) < 80:
            text += " Once each turn only."
        return text

    def _record_payload(self, record: PacketRecord) -> dict[str, Any]:
        payload = dict(record.fields)
        payload.update(record.sections)
        return payload

    def _updates_from_payload(self, card: Any, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for key in ["rules_text", "flavor_text", "design_notes", "art_direction", "type_line", "template_id"]:
            value = str(payload.get(key) or "").strip()
            if value and value != str(card[key] or "").strip():
                updates[key] = value
        if payload.get("keywords"):
            keywords = [part.strip().lower().replace(" ", "_") for part in str(payload["keywords"]).replace(";", ",").split(",") if part.strip()]
            if keywords:
                updates["keywords_json"] = json.dumps(keywords)
        return updates
