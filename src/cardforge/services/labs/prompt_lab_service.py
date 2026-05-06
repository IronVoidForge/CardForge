from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.llm.markdown_sections import parse_markdown_sections
from cardforge.services.llm.offline_simulator import OfflineCardLLMSimulator
from cardforge.services.llm.packet_parser import parse_card_records
from cardforge.services.batches.card_payload_parser import record_to_card_payload
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService
from cardforge.services.review.review_service import ReviewService


@dataclass(frozen=True)
class PromptLabCaseSpec:
    project_slug: str
    template_key: str
    target_type: str = "project"
    target_id: str = ""
    notes: str = ""


class PromptLabService:
    """Isolated prompt experimentation for CardForge prompt templates.

    Prompt Lab cases intentionally write under ``99_prompt_lab`` and do not mutate
    cards, batches, or prompt templates.  Accepted runs generate promotion notes
    that humans can apply deliberately.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.prompts = PromptTemplateService(self.db)
        self.simulator = OfflineCardLLMSimulator()

    def create_case(self, spec: PromptLabCaseSpec) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(spec.project_slug, conn=conn)
            template = self.prompts.load_template(spec.project_slug, spec.template_key)
            context = self._context_for_target(conn, project_id=project["id"], spec=spec)
            system_prompt = _safe_format(template.system_template, context)
            user_prompt = _safe_format(template.user_template, context)
            case_key = next_key(conn, "prompt_lab_cases", "case_key", "PLAB", where="project_id = ?", params=(project["id"],))
            case_dir = self.asset_store.project_root(spec.project_slug) / "99_prompt_lab" / "cases" / case_key
            self.asset_store.write_json(case_dir / "context.json", context)
            self.asset_store.write_text(case_dir / "original_system_prompt.md", system_prompt + "\n")
            self.asset_store.write_text(case_dir / "original_user_prompt.md", user_prompt + "\n")
            self.asset_store.write_text(case_dir / "candidate_prompt.md", _candidate_prompt_markdown(system_prompt, user_prompt, spec.notes))
            manifest = {
                "case_key": case_key,
                "project_slug": spec.project_slug,
                "template_key": spec.template_key,
                "task_type": template.task,
                "target_type": spec.target_type,
                "target_id": spec.target_id,
                "writes_production_artifacts": False,
                "notes": spec.notes,
            }
            self.asset_store.write_json(case_dir / "case_manifest.json", manifest)
            conn.execute(
                """
                INSERT INTO prompt_lab_cases(project_id, case_key, template_key, task_type, target_type, target_id, case_dir, notes)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project["id"],
                    case_key,
                    spec.template_key,
                    template.task,
                    spec.target_type,
                    spec.target_id,
                    self.asset_store.relative_to_workspace(case_dir),
                    spec.notes,
                ),
            )
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=None,
                target_type="prompt_lab_case",
                target_id=case_key,
                review_type="prompt_lab",
                title=f"Prompt Lab case {case_key}: {spec.template_key}",
                description="Run prompt variants, compare outputs, and promote only proven changes.",
                metadata=manifest,
                conn=conn,
            )
            return {**manifest, "case_dir": self.asset_store.relative_to_workspace(case_dir)}

    def list_cases(self, project_slug: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            rows = conn.execute(
                "SELECT * FROM prompt_lab_cases WHERE project_id = ? ORDER BY id DESC", (project["id"],)
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    def get_case(self, project_slug: str, case_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                "SELECT * FROM prompt_lab_cases WHERE project_id = ? AND case_key = ?", (project["id"], case_key)
            ).fetchone()
            if row is None:
                raise KeyError(f"Prompt Lab case not found: {case_key}")
            return row
        finally:
            if close:
                conn.close()

    def run_case(self, project_slug: str, case_key: str, *, variant_notes: str = "", use_mock: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            run_key = next_key(conn, "prompt_lab_runs", "run_key", "RUN", where="case_id = ?", params=(case["id"],))
            case_dir = self.asset_store.safe_resolve(case["case_dir"])
            run_dir = case_dir / "runs" / run_key
            candidate_text = self._candidate_text(case_dir / "candidate_prompt.md", variant_notes=variant_notes)
            self.asset_store.write_text(run_dir / "candidate_prompt.md", candidate_text)
            system_prompt, user_prompt = _split_candidate_prompt(candidate_text)
            raw_response = self._mock_response(case, system_prompt=system_prompt, user_prompt=user_prompt) if use_mock else ""
            if not use_mock:
                raise RuntimeError("Live Prompt Lab runs are not wired yet. Use --mock until LM Studio live mode is enabled.")
            self.asset_store.write_text(run_dir / "raw_response.md", raw_response)
            parsed, metrics = self._parse_lab_response(raw_response, task_type=case["task_type"])
            self.asset_store.write_json(run_dir / "parsed_response.json", parsed)
            self.asset_store.write_json(run_dir / "metrics.json", metrics)
            conn.execute(
                """
                INSERT INTO prompt_lab_runs(case_id, run_key, variant_label, candidate_prompt_path, raw_response_path, parsed_response_json, metrics_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case["id"],
                    run_key,
                    variant_notes[:120],
                    self.asset_store.relative_to_workspace(run_dir / "candidate_prompt.md"),
                    self.asset_store.relative_to_workspace(run_dir / "raw_response.md"),
                    json.dumps(parsed, ensure_ascii=False),
                    json.dumps(metrics, ensure_ascii=False),
                ),
            )
            self.asset_store.write_json(run_dir / "run_manifest.json", {"run_key": run_key, "case_key": case_key, "metrics": metrics})
            return {"case_key": case_key, "run_key": run_key, "status": "unreviewed", "metrics": metrics, "run_dir": self.asset_store.relative_to_workspace(run_dir)}

    def compare_runs(self, project_slug: str, case_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            rows = conn.execute("SELECT * FROM prompt_lab_runs WHERE case_id = ? ORDER BY id", (case["id"],)).fetchall()
            runs = []
            for row in rows:
                metrics = _json_loads(row["metrics_json"], {})
                runs.append({"run_key": row["run_key"], "status": row["status"], "variant_label": row["variant_label"], **metrics})
            comparison = {"case_key": case_key, "run_count": len(runs), "runs": runs, "accepted_run_key": case["accepted_run_key"]}
            case_dir = self.asset_store.safe_resolve(case["case_dir"])
            self.asset_store.write_json(case_dir / "comparison.json", comparison)
            self.asset_store.write_text(case_dir / "comparison.md", _prompt_comparison_markdown(comparison))
            return comparison

    def mark_run(self, project_slug: str, case_key: str, run_key: str, *, status: str, notes: str = "") -> dict[str, Any]:
        if status not in {"accepted", "rejected", "maybe", "unreviewed"}:
            raise ValueError("Prompt Lab run status must be accepted, rejected, maybe, or unreviewed.")
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            run = conn.execute("SELECT * FROM prompt_lab_runs WHERE case_id = ? AND run_key = ?", (case["id"], run_key)).fetchone()
            if run is None:
                raise KeyError(f"Prompt Lab run not found: {run_key}")
            conn.execute("UPDATE prompt_lab_runs SET status = ?, notes = ? WHERE id = ?", (status, notes, run["id"]))
            if status == "accepted":
                conn.execute(
                    "UPDATE prompt_lab_cases SET accepted_run_key = ?, status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (run_key, case["id"]),
                )
            return {"case_key": case_key, "run_key": run_key, "status": status, "notes": notes}

    def write_promotion_note(self, project_slug: str, case_key: str, *, run_key: str | None = None) -> dict[str, Any]:
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            selected_run = run_key or case["accepted_run_key"]
            if not selected_run:
                raise ValueError("No run supplied and no accepted run exists for this Prompt Lab case.")
            run = conn.execute("SELECT * FROM prompt_lab_runs WHERE case_id = ? AND run_key = ?", (case["id"], selected_run)).fetchone()
            if run is None:
                raise KeyError(f"Prompt Lab run not found: {selected_run}")
            note_dir = self.asset_store.project_root(project_slug) / "99_prompt_lab" / "promotion_notes"
            note_path = note_dir / f"{case_key}_{selected_run}.md"
            note = _promotion_note_markdown(case, run)
            self.asset_store.write_text(note_path, note)
            return {"case_key": case_key, "run_key": selected_run, "promotion_note_path": self.asset_store.relative_to_workspace(note_path)}

    def _context_for_target(self, conn: Connection, *, project_id: int, spec: PromptLabCaseSpec) -> dict[str, Any]:
        context: dict[str, Any] = {
            "project_slug": spec.project_slug,
            "request_text": spec.notes or "Prompt Lab experiment",
            "count": 3,
            "set_code": "SET001",
            "set_name": "Prompt Lab Set",
            "card_key": spec.target_id,
            "name": "",
            "card_type": "creature",
            "rarity": "common",
            "faction": "",
            "missing_fields": "",
            "rules_text": "",
            "flavor_text": "",
            "art_direction": "",
            "findings": "[]",
            "recommendations": "[]",
        }
        if spec.target_type == "card" and spec.target_id:
            card = conn.execute(
                """
                SELECT c.*, s.set_code, s.name AS set_name FROM cards c
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND c.card_key = ?
                """,
                (project_id, spec.target_id),
            ).fetchone()
            if card:
                context.update({key: card[key] for key in card.keys() if key in context or key in {"set_code", "set_name"}})
                context["name"] = card["name"]
                context["card_type"] = card["card_type"]
                context["rarity"] = card["rarity"]
                context["faction"] = card["faction"]
                context["rules_text"] = card["rules_text"]
                context["flavor_text"] = card["flavor_text"]
                context["art_direction"] = card["art_direction"]
        if spec.target_type == "set" and spec.target_id:
            set_row = conn.execute("SELECT * FROM sets WHERE project_id = ? AND set_code = ?", (project_id, spec.target_id)).fetchone()
            if set_row:
                context["set_code"] = set_row["set_code"]
                context["set_name"] = set_row["name"]
        return context

    def _candidate_text(self, path: Path, *, variant_notes: str) -> str:
        base = self.asset_store.safe_resolve(path).read_text(encoding="utf-8")
        if not variant_notes.strip():
            return base
        return base.rstrip() + "\n\n# Variant Notes\n" + variant_notes.strip() + "\n"

    def _mock_response(self, case: Row, *, system_prompt: str, user_prompt: str) -> str:
        task = str(case["task_type"] or "").strip()
        if task == "card_batch":
            return self.simulator.card_batch_packet(count=3, request_text=user_prompt, batch_key=f"LAB_{case['case_key']}")
        if task in {"card_autofill", "card_refinement"}:
            name = _extract_input(user_prompt, "name") or "Lab Card"
            card_type = _extract_input(user_prompt, "card_type") or "creature"
            rules = self.simulator.repaired_rules_text(name=name, original_rules=_extract_input(user_prompt, "current_rules_text"), reason="Prompt Lab refinement")
            return f"""[[CARDFORGE_PACKET]]
task: {task}
version: 1

[[CARDFORGE_RECORD]]
type: card
name: {name}
card_type: {card_type}
rarity: common
faction: Lab
cost: 2
attack: 1
health: 3
template_id: default_{card_type}_front_v1
[[SECTION rules_text]]
{rules}
[[/SECTION]]
[[SECTION art_direction]]
Lab-tested illustration prompt, no text, no border, no logo.
[[/SECTION]]
[[/CARDFORGE_RECORD]]
[[/CARDFORGE_PACKET]]
"""
        return "[[CARDFORGE_PACKET]]\ntask: lab_note\nversion: 1\n[[/CARDFORGE_PACKET]]\n"

    def _parse_lab_response(self, raw_response: str, *, task_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            records = parse_card_records(raw_response, expected_task=task_type if task_type in {"card_batch", "card_autofill", "card_refinement"} else None)
            cards = [record_to_card_payload(record) for record in records]
            metrics = {
                "parse_status": "parsed",
                "card_record_count": len(cards),
                "response_chars": len(raw_response),
                "avg_rules_chars": round(sum(len(str(card.get("rules_text", ""))) for card in cards) / max(1, len(cards)), 2),
            }
            metrics["score_100"] = _prompt_run_score(metrics)
            return {"cards": cards}, metrics
        except Exception as exc:
            metrics = {"parse_status": "failed", "response_chars": len(raw_response), "error": str(exc), "score_100": 0}
            return {"error": str(exc), "raw_excerpt": raw_response[:1000]}, metrics


def _prompt_run_score(metrics: dict[str, Any]) -> int:
    if metrics.get("parse_status") != "parsed":
        return 0
    score = 45
    card_count = int(metrics.get("card_record_count") or 0)
    if card_count:
        score += min(25, card_count * 8)
    avg_rules = float(metrics.get("avg_rules_chars") or 0)
    if 20 <= avg_rules <= 260:
        score += 20
    elif avg_rules:
        score += 8
    response_chars = int(metrics.get("response_chars") or 0)
    if response_chars > 120:
        score += 10
    return max(0, min(100, score))


def _safe_format(template: str, context: dict[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    safe_context = {key: _stringify(value) for key, value in context.items()}
    return str(template or "").format_map(SafeDict(safe_context)).strip()


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "")


def _candidate_prompt_markdown(system_prompt: str, user_prompt: str, notes: str) -> str:
    return "\n".join([
        "# System Prompt", system_prompt.strip(), "", "# User Prompt", user_prompt.strip(), "", "# Lab Notes", notes.strip(), ""
    ])


def _split_candidate_prompt(text: str) -> tuple[str, str]:
    doc = parse_markdown_sections(text)
    system = doc.section("system_prompt") or "You are CardForge's local card design model."
    user = doc.section("user_prompt") or text
    variant = doc.section("variant_notes")
    if variant:
        user = user.rstrip() + "\n\nVARIANT_NOTES:\n" + variant.strip()
    return system, user


def _extract_input(user_prompt: str, key: str) -> str:
    needle = key.lower().replace("_", "-")
    for raw in user_prompt.splitlines():
        line = raw.strip().lstrip("-* ").strip()
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        if left.strip().lower().replace("_", "-") == needle:
            return right.strip()
    return ""


def _prompt_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = ["# Prompt Lab Comparison", "", f"- Case: {comparison['case_key']}", f"- Runs: {comparison['run_count']}", "", "| Run | Status | Cards | Parse | Avg Rules Chars | Variant |", "|---|---:|---:|---|---:|---|"]
    for run in comparison["runs"]:
        lines.append(f"| {run['run_key']} | {run['status']} | {run.get('card_record_count', 0)} | {run.get('parse_status', '')} | {run.get('avg_rules_chars', '')} | {run.get('variant_label', '')} |")
    return "\n".join(lines) + "\n"


def _promotion_note_markdown(case: Row, run: Row) -> str:
    metrics = _json_loads(run["metrics_json"], {})
    return "\n".join([
        "# Prompt Lab Promotion Note", "", f"- Case: {case['case_key']}", f"- Template: {case['template_key']}", f"- Accepted run: {run['run_key']}", f"- Target: {case['target_type']} / {case['target_id']}", "", "## Why this matters", run["notes"] or "Add human review notes before applying this change to production prompts.", "", "## Metrics", "```json", json.dumps(metrics, indent=2, ensure_ascii=False), "```", "", "## Suggested production change", "Review the run's candidate prompt and output, then copy only the proven wording into the relevant prompt template.", "",
    ])


def _row_to_dict(row: Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_loads(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return default
