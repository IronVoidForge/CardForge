from __future__ import annotations

import json
import re
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.integrations.lmstudio import LMStudioClient
from cardforge.schemas.card import CardCost, CardRecord, CardStats
from cardforge.services.cards.card_service import CardService
from cardforge.services.llm.llm_request_log import LLMRequestLog
from cardforge.services.llm.mock_responses import build_mock_card_batch_packet
from cardforge.services.llm.packet_parser import PacketParseError, PacketRecord, parse_card_records
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService
from cardforge.services.sets.set_service import SetService


class CardBatchService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.sets = SetService(self.db)
        self.cards = CardService(self.db)
        self.llm_log = LLMRequestLog(self.db)

    def generate_simulated_batch(
        self,
        project_slug: str,
        set_code: str,
        *,
        count: int,
        request_text: str,
    ) -> dict[str, Any]:
        return self.generate_batch(project_slug, set_code, count=count, request_text=request_text, use_mock=True)

    def generate_batch(
        self,
        project_slug: str,
        set_code: str,
        *,
        count: int,
        request_text: str,
        use_mock: bool = True,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if count < 1 or count > 30:
            raise ValueError("Batch count must be between 1 and 30. Use 10-15 for normal prototype batches.")
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            batch_key = next_key(conn, "card_batches", "batch_key", "BATCH", where="set_id = ?", params=(set_row["id"],))
            batch_root = self.asset_store.project_root(project_slug) / "batches" / batch_key
            request_md = batch_root / "request.md"
            self.asset_store.write_text(request_md, request_text.strip() + "\n")
            conn.execute(
                """
                INSERT INTO card_batches(set_id, batch_key, request_text, request_json, target_count, status)
                VALUES(?, ?, ?, ?, ?, 'generating')
                """,
                (
                    set_row["id"],
                    batch_key,
                    request_text,
                    json.dumps({"count": count, "use_mock": use_mock}, ensure_ascii=False),
                    count,
                ),
            )
            batch = self.get_batch(project_slug, batch_key, conn=conn)
            system_prompt, user_prompt = self._build_batch_prompt(set_row=set_row, count=count, request_text=request_text)
            llm_request_id = self.llm_log.create(
                conn,
                project_id=project["id"],
                set_id=set_row["id"],
                card_id=None,
                batch_id=batch["id"],
                project_slug=project_slug,
                task_type="card_batch",
                model=model or ("mock-cardforge-model" if use_mock else self.db.settings.lmstudio_model),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=self.db.settings.lmstudio_max_tokens,
            )
            try:
                raw_response = self._get_batch_response(
                    batch_key=batch_key,
                    request_text=request_text,
                    count=count,
                    use_mock=use_mock,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                )
                records = parse_card_records(raw_response, expected_task="card_batch")
                parsed_cards = [self._record_to_card_payload(record) for record in records]
                self.llm_log.complete(
                    conn,
                    request_id=llm_request_id,
                    project_slug=project_slug,
                    raw_response=raw_response,
                    parsed_payload={"cards": parsed_cards},
                )
            except Exception as exc:
                self.llm_log.fail(conn, request_id=llm_request_id, error=str(exc))
                conn.execute(
                    "UPDATE card_batches SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (batch["id"],),
                )
                raise

            raw_path = batch_root / "raw_response.md"
            parsed_path = batch_root / "parsed_cards.json"
            self.asset_store.write_text(raw_path, raw_response)
            self.asset_store.write_json(parsed_path, {"cards": parsed_cards})
            created_cards: list[dict[str, Any]] = []
            for payload in parsed_cards:
                record = self._payload_to_card_record(payload)
                card = self.cards.create_card_from_record(
                    project_slug,
                    set_code,
                    record,
                    batch_id=batch["id"],
                    source="llm_mock_generation" if use_mock else "llm_generation",
                    review_description="Generated card needs text/rules review before art or final rendering.",
                    conn=conn,
                )
                created_cards.append({key: card[key] for key in card.keys()})

            validation_summary = self.validate_batch(project_slug, batch_key, conn=conn)
            status = "validated" if validation_summary["valid_card_count"] == len(created_cards) else "validation_failed"
            manifest = {
                "batch_key": batch_key,
                "project_slug": project_slug,
                "set_code": set_code,
                "target_count": count,
                "created_card_count": len(created_cards),
                "use_mock": use_mock,
                "llm_request_id": llm_request_id,
                "raw_response_path": self.asset_store.relative_to_workspace(raw_path),
                "parsed_json_path": self.asset_store.relative_to_workspace(parsed_path),
                "validation_summary": validation_summary,
                "cards": [card["card_key"] for card in created_cards],
            }
            manifest_path = batch_root / "CARD_BATCH_MANIFEST.json"
            self.asset_store.write_json(manifest_path, manifest)
            conn.execute(
                """
                UPDATE card_batches
                SET status = ?, raw_response_path = ?, parsed_json_path = ?, validation_summary_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    self.asset_store.relative_to_workspace(raw_path),
                    self.asset_store.relative_to_workspace(parsed_path),
                    json.dumps(validation_summary, ensure_ascii=False),
                    batch["id"],
                ),
            )
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=set_row["id"],
                target_type="batch",
                target_id=batch_key,
                review_type="batch_text",
                title=f"Review generated batch {batch_key}",
                description=f"Generated {len(created_cards)} card(s). Review type mix, rules clarity, and batch health.",
                metadata=manifest,
                conn=conn,
            )
            return manifest

    def get_batch(self, project_slug: str, batch_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                """
                SELECT b.* FROM card_batches b
                JOIN sets s ON s.id = b.set_id
                WHERE s.project_id = ? AND b.batch_key = ?
                """,
                (project["id"], batch_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Batch not found: {batch_key}")
            return row
        finally:
            if close:
                conn.close()

    def list_batches(self, project_slug: str, set_code: str | None = None) -> list[Row]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            if set_code:
                set_row = self.sets.get_set(project_slug, set_code, conn=conn)
                return list(conn.execute("SELECT * FROM card_batches WHERE set_id = ? ORDER BY batch_key", (set_row["id"],)))
            return list(conn.execute("SELECT b.* FROM card_batches b JOIN sets s ON s.id = b.set_id WHERE s.project_id = ? ORDER BY b.batch_key", (project["id"],)))

    def validate_batch(self, project_slug: str, batch_key: str, *, conn: Connection | None = None) -> dict[str, Any]:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            batch = self.get_batch(project_slug, batch_key, conn=conn)
            cards = list(conn.execute("SELECT * FROM cards WHERE batch_id = ? ORDER BY card_key", (batch["id"],)))
            card_reports: list[dict[str, Any]] = []
            for card in cards:
                report = self.cards.validator.validate(project_slug, card)
                status = CardStatus.VALIDATED.value if report.valid else CardStatus.NEEDS_REPAIR.value
                conn.execute("UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, card["id"]))
                report_path = self.asset_store.project_root(project_slug) / "cards" / card["card_key"] / "validation_report.json"
                self.asset_store.write_json(report_path, report.model_dump())
                card_reports.append(report.model_dump())
            error_count = sum(1 for report in card_reports for issue in report["issues"] if issue["severity"] == "error")
            warning_count = sum(1 for report in card_reports for issue in report["issues"] if issue["severity"] == "warning")
            summary = {
                "batch_key": batch_key,
                "card_count": len(cards),
                "valid_card_count": sum(1 for report in card_reports if report["valid"]),
                "error_count": error_count,
                "warning_count": warning_count,
                "reports": card_reports,
            }
            self.asset_store.write_json(self.asset_store.project_root(project_slug) / "batches" / batch_key / "validation_report.json", summary)
            conn.execute(
                "UPDATE card_batches SET validation_summary_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(summary, ensure_ascii=False), batch["id"]),
            )
            if close:
                conn.commit()
            return summary
        finally:
            if close:
                conn.close()

    def _get_batch_response(
        self,
        *,
        batch_key: str,
        request_text: str,
        count: int,
        use_mock: bool,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        if use_mock:
            return build_mock_card_batch_packet(batch_key=batch_key, request_text=request_text, count=count)
        result = LMStudioClient(self.db.settings).chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
        )
        if not result.ok:
            raise RuntimeError(result.error or "LM Studio call failed.")
        return result.text

    def _build_batch_prompt(self, *, set_row: Row, count: int, request_text: str) -> tuple[str, str]:
        system = """
You are CardForge's local card design model. Return only one CARDFORGE packet. Do not generate final card images.
Use the requested card count. Keep rules text concise enough to fit a physical card.
Each record must include name, card_type, rarity, faction, cost, template_id, and sections for rules_text, design_notes, and art_direction.
        """.strip()
        user = f"""
Generate {count} prototype cards for set {set_row['set_code']} / {set_row['name']}.

USER REQUEST:
{request_text}

PACKET SHAPE:
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
Illustration-only prompt. No text, no border, no logo.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]
        """.strip()
        return system, user

    def _record_to_card_payload(self, record: PacketRecord) -> dict[str, Any]:
        fields = {key.lower(): value for key, value in record.fields.items()}
        sections = {key.lower(): value for key, value in record.sections.items()}
        payload = dict(fields)
        for section in ("rules_text", "flavor_text", "design_notes", "art_direction"):
            if section in sections:
                payload[section] = sections[section]
        return payload

    def _payload_to_card_record(self, payload: dict[str, Any]) -> CardRecord:
        card_type = str(payload.get("card_type") or payload.get("type_line") or "creature").strip().lower()
        if card_type.startswith("creature"):
            card_type = "creature"
        cost = self._coerce_cost(payload.get("cost"))
        attack = self._coerce_int(payload.get("attack"))
        health = self._coerce_int(payload.get("health"))
        keywords = self._coerce_string_list(payload.get("keywords"))
        subtypes = self._coerce_string_list(payload.get("subtypes"))
        mechanics = self._coerce_json_list(payload.get("mechanics"))
        return CardRecord(
            name=str(payload.get("name") or "Unnamed Card").strip(),
            card_type=card_type,
            rarity=str(payload.get("rarity") or "common").strip().lower(),
            faction=str(payload.get("faction") or "").strip(),
            type_line=str(payload.get("type_line") or "").strip(),
            cost=cost,
            stats=CardStats(attack=attack, health=health),
            rules_text=str(payload.get("rules_text") or "").strip(),
            flavor_text=str(payload.get("flavor_text") or "").strip(),
            keywords=keywords,
            mechanics=mechanics,
            subtypes=subtypes,
            design_notes=str(payload.get("design_notes") or "").strip(),
            art_direction=str(payload.get("art_direction") or "").strip(),
            template_id=str(payload.get("template_id") or "").strip(),
            back_template_id=str(payload.get("back_template_id") or "default_card_back_v1").strip(),
        )

    def _coerce_cost(self, value: Any) -> CardCost:
        if isinstance(value, CardCost):
            return value
        if isinstance(value, dict):
            return CardCost(**value)
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("{"):
                try:
                    return CardCost(**json.loads(text))
                except json.JSONDecodeError:
                    pass
            match = re.search(r"\d+", text)
            return CardCost(generic=int(match.group(0)) if match else 0, display=text or "0")
        if isinstance(value, int):
            return CardCost(generic=value)
        return CardCost()

    def _coerce_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None

    def _coerce_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                payload = json.loads(text)
                if isinstance(payload, list):
                    return [str(item).strip().lower() for item in payload if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip().lower().replace(" ", "_") for part in re.split(r"[,;\n]+", text) if part.strip()]

    def _coerce_json_list(self, value: Any) -> list[dict[str, Any]]:
        if not value:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                payload = json.loads(value)
                if isinstance(payload, list):
                    return [item for item in payload if isinstance(item, dict)]
            except json.JSONDecodeError:
                return []
        return []
