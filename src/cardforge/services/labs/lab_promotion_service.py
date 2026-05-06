from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.observability.audit_log_service import AuditLogService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService
from cardforge.services.review.review_service import ReviewService


class LabPromotionService:
    """Review gate for lab evidence before production changes are applied."""

    VALID_STATUSES = {"requested", "approved", "rejected", "applied"}

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.asset_store = AssetStore(self.db.settings)
        self.audit = AuditLogService(self.db)
        self.versions = PromptTemplateVersionService(self.db)

    def create_prompt_template_request(
        self,
        project_slug: str,
        case_key: str,
        *,
        run_key: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            self.versions.sync_project(project_slug)
            case = self._get_prompt_case(conn, project_id=project["id"], case_key=case_key)
            selected_run = (run_key or case["accepted_run_key"] or "").strip()
            if not selected_run:
                raise ValueError("Prompt Lab run must be marked accepted before promotion.")
            run = self._get_prompt_run(conn, case_id=case["id"], run_key=selected_run)
            if run["status"] != "accepted":
                raise ValueError("Prompt Lab run must be marked accepted before promotion.")
            request_key = next_key(conn, "lab_promotion_requests", "request_key", "PROMO", where="project_id = ?", params=(project["id"],))
            evidence = self._prompt_evidence(case, run)
            request_dir = self.asset_store.project_root(project_slug) / "99_prompt_lab" / "promotion_requests"
            proposal_path = request_dir / f"{request_key}_{case_key}_{selected_run}.md"
            evidence_path = request_dir / f"{request_key}_{case_key}_{selected_run}_evidence.json"
            self.asset_store.write_json(evidence_path, evidence)
            self.asset_store.write_text(proposal_path, _prompt_promotion_markdown(request_key, case, run, notes, evidence))
            review_id = ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=None,
                target_type="lab_promotion_request",
                target_id=request_key,
                review_type="prompt_lab_promotion",
                title=f"Review Prompt Lab promotion {request_key}",
                description="Approve before applying this lab lesson as a new prompt template version.",
                metadata={"request_key": request_key, "case_key": case_key, "run_key": selected_run},
                conn=conn,
            )
            conn.execute(
                """
                INSERT INTO lab_promotion_requests(
                    project_id, request_key, lab_type, case_key, run_key, template_key, target_type, target_id,
                    proposal_markdown_path, evidence_json_path, status, review_item_id, notes
                ) VALUES(?, ?, 'prompt_lab', ?, ?, ?, 'prompt_template', ?, ?, ?, 'requested', ?, ?)
                """,
                (
                    project["id"], request_key, case_key, selected_run, case["template_key"], case["template_key"],
                    self.asset_store.relative_to_workspace(proposal_path), self.asset_store.relative_to_workspace(evidence_path),
                    int(review_id), notes,
                ),
            )
            self.audit.record(
                conn,
                project_id=project["id"],
                event_type="lab_promotion_requested",
                target_type="lab_promotion_request",
                target_id=request_key,
                payload={"lab_type": "prompt_lab", "case_key": case_key, "run_key": selected_run},
            )
            return {
                "project_slug": project_slug,
                "request_key": request_key,
                "case_key": case_key,
                "run_key": selected_run,
                "status": "requested",
                "proposal_markdown_path": self.asset_store.relative_to_workspace(proposal_path),
                "evidence_json_path": self.asset_store.relative_to_workspace(evidence_path),
                "review_item_id": review_id,
            }

    def list_requests(self, project_slug: str, *, status: str | None = None) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            sql = "SELECT * FROM lab_promotion_requests WHERE project_id = ?"
            params: list[Any] = [project["id"]]
            if status:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY created_at DESC, id DESC"
            return [self._to_dict(row) for row in conn.execute(sql, params).fetchall()]

    def approve_request(self, project_slug: str, request_key: str, *, notes: str = "") -> dict[str, Any]:
        return self._set_status(project_slug, request_key, status="approved", notes=notes)

    def reject_request(self, project_slug: str, request_key: str, *, notes: str = "") -> dict[str, Any]:
        return self._set_status(project_slug, request_key, status="rejected", notes=notes)

    def approve(self, project_slug: str, request_key: str, *, notes: str = "") -> dict[str, Any]:
        return self.approve_request(project_slug, request_key, notes=notes)

    def reject(self, project_slug: str, request_key: str, *, notes: str = "") -> dict[str, Any]:
        return self.reject_request(project_slug, request_key, notes=notes)

    def apply_request(self, project_slug: str, request_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            request = self.get_request(conn, project_id=project["id"], request_key=request_key)
            if request["status"] != "approved":
                raise ValueError("Lab promotion request must be approved before it can be applied.")
            if request["lab_type"] != "prompt_lab":
                raise ValueError("Only Prompt Lab / Only prompt_lab promotions can be applied automatically right now.")
            case = self._get_prompt_case(conn, project_id=project["id"], case_key=request["case_key"])
            run = self._get_prompt_run(conn, case_id=case["id"], run_key=request["run_key"])
            markdown = _template_markdown_with_lab_note(
                self.versions.get_active_template_markdown(project_slug, request["template_key"]),
                case=case,
                run=run,
                request=request,
            )
            version = self.versions.create_version(
                project_slug,
                template_key=request["template_key"],
                markdown=markdown,
                source="prompt_lab",
                source_target_type="prompt_lab_run",
                source_target_id=f"{request['case_key']}:{request['run_key']}",
                summary=request["notes"] or run["notes"] or "Accepted Prompt Lab promotion.",
                activate=True,
                conn=conn,
            )
            conn.execute(
                "UPDATE lab_promotion_requests SET status = 'applied', applied_version_key = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (version.version_key, request["id"]),
            )
            self.audit.record(
                conn,
                project_id=project["id"],
                event_type="lab_promotion_applied",
                target_type="lab_promotion_request",
                target_id=request_key,
                payload={"version_key": version.version_key, "template_key": request["template_key"]},
            )
            return {"project_slug": project_slug, "request_key": request_key, "version_key": version.version_key, "template_key": version.template_key, "status": "applied"}

    def get_request(self, conn: Connection, *, project_id: int, request_key: str) -> Row:
        row = conn.execute("SELECT * FROM lab_promotion_requests WHERE project_id = ? AND request_key = ?", (project_id, request_key)).fetchone()
        if row is None:
            raise KeyError(f"Lab promotion request not found: {request_key}")
        return row

    def _set_status(self, project_slug: str, request_key: str, *, status: str, notes: str) -> dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported lab promotion status: {status}")
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            request = self.get_request(conn, project_id=project["id"], request_key=request_key)
            conn.execute(
                "UPDATE lab_promotion_requests SET status = ?, notes = CASE WHEN ? != '' THEN ? ELSE notes END, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, notes, notes, request["id"]),
            )
            self.audit.record(
                conn,
                project_id=project["id"],
                event_type=f"lab_promotion_{status}",
                target_type="lab_promotion_request",
                target_id=request_key,
                payload={"lab_type": request["lab_type"], "notes": notes},
            )
            return {"project_slug": project_slug, "request_key": request_key, "status": status, "notes": notes}

    def _get_prompt_case(self, conn: Connection, *, project_id: int, case_key: str) -> Row:
        row = conn.execute("SELECT * FROM prompt_lab_cases WHERE project_id = ? AND case_key = ?", (project_id, case_key)).fetchone()
        if row is None:
            raise KeyError(f"Prompt Lab case not found: {case_key}")
        return row

    def _get_prompt_run(self, conn: Connection, *, case_id: int, run_key: str) -> Row:
        row = conn.execute("SELECT * FROM prompt_lab_runs WHERE case_id = ? AND run_key = ?", (case_id, run_key)).fetchone()
        if row is None:
            raise KeyError(f"Prompt Lab run not found: {run_key}")
        return row

    def _prompt_evidence(self, case: Row, run: Row) -> dict[str, Any]:
        return {
            "case_key": case["case_key"],
            "run_key": run["run_key"],
            "template_key": case["template_key"],
            "task_type": case["task_type"],
            "target_type": case["target_type"],
            "target_id": case["target_id"],
            "run_status": run["status"],
            "variant_label": run["variant_label"],
            "notes": run["notes"],
            "metrics": _json_loads(run["metrics_json"], {}),
            "parsed_response": _json_loads(run["parsed_response_json"], {}),
        }

    def _to_dict(self, row: Row) -> dict[str, Any]:
        payload = {key: row[key] for key in row.keys()}
        payload["has_evidence"] = bool(str(payload.get("evidence_json_path") or ""))
        return payload


def _prompt_promotion_markdown(request_key: str, case: Row, run: Row, notes: str, evidence: dict[str, Any]) -> str:
    return "\n".join([
        "# Prompt Lab Promotion Request", "", f"- Request: {request_key}", f"- Template: {case['template_key']}", f"- Case: {case['case_key']}", f"- Run: {run['run_key']}", "", "## Operator Notes", notes or run["notes"] or "Review the accepted run and approve only reusable prompt guidance.", "", "## Evidence", "```json", json.dumps(evidence, indent=2, ensure_ascii=False), "```", "", "## Gate", "This request must be approved before it can create and activate a new prompt-template version.", "",
    ])


def _template_markdown_with_lab_note(active_markdown: str, *, case: Row, run: Row, request: Row) -> str:
    insertion = "\n\n## Accepted Prompt Lab Guidance\n"
    insertion += (request["notes"] or run["notes"] or "Apply the accepted Prompt Lab guidance.").strip()
    if run["variant_label"]:
        insertion += "\n\nVariant notes: " + str(run["variant_label"]).strip()
    insertion += f"\n\nEvidence: {case['case_key']} / {run['run_key']}."
    if "# Sources" in active_markdown:
        active_markdown = active_markdown.replace("# Sources", insertion + "\n\n# Sources", 1)
    else:
        active_markdown = active_markdown.rstrip() + insertion + "\n"
    if "# Sources" in active_markdown and f"- Prompt Lab {case['case_key']} / {run['run_key']}" not in active_markdown:
        active_markdown = active_markdown.rstrip() + f"\n- Prompt Lab {case['case_key']} / {run['run_key']}\n"
    return active_markdown.rstrip() + "\n"


def _json_loads(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return default
