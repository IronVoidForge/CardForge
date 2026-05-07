from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.llm.markdown_sections import parse_markdown_sections
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService


@dataclass(frozen=True)
class DiffLine:
    kind: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "text": self.text}


class PromptTemplateStudioService:
    """Read/write view-model service for prompt template version review.

    The studio intentionally works on prompt *versions*, not production prompt
    template files directly. Active templates can be inspected, proposed versions
    can be edited, and only approved versions can be activated.
    """

    EDITABLE_STATUSES = {"proposed", "approved"}

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.asset_store = AssetStore(self.db.settings)
        self.versions = PromptTemplateVersionService(self.db)

    def dashboard(self, project_slug: str) -> dict[str, Any]:
        self.versions.sync_project(project_slug)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            templates = [dict(row) for row in conn.execute(
                """
                SELECT pt.template_key, pt.name, pt.task_type, pt.status,
                       active.version_key AS active_version_key,
                       active.version_number AS active_version_number,
                       pending.pending_count,
                       rejected.rejected_count
                FROM prompt_templates pt
                LEFT JOIN prompt_template_versions active
                  ON active.project_id = pt.project_id
                 AND active.template_key = pt.template_key
                 AND active.status = 'active'
                LEFT JOIN (
                  SELECT project_id, template_key, COUNT(*) AS pending_count
                  FROM prompt_template_versions
                  WHERE status IN ('proposed', 'approved')
                  GROUP BY project_id, template_key
                ) pending
                  ON pending.project_id = pt.project_id AND pending.template_key = pt.template_key
                LEFT JOIN (
                  SELECT project_id, template_key, COUNT(*) AS rejected_count
                  FROM prompt_template_versions
                  WHERE status = 'rejected'
                  GROUP BY project_id, template_key
                ) rejected
                  ON rejected.project_id = pt.project_id AND rejected.template_key = pt.template_key
                WHERE pt.project_id = ?
                ORDER BY pt.template_key
                """,
                (project["id"],),
            )]
            versions = [dict(row) for row in conn.execute(
                """
                SELECT version_key, template_key, version_number, status, source,
                       source_target_type, source_target_id, summary, markdown_path, created_at
                FROM prompt_template_versions
                WHERE project_id = ?
                ORDER BY template_key, version_number DESC
                """,
                (project["id"],),
            )]
            promotions = [dict(row) for row in conn.execute(
                """
                SELECT request_key, lab_type, case_key, run_key, template_key, target_type,
                       target_id, status, applied_version_key, notes, created_at
                FROM lab_promotion_requests
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """,
                (project["id"],),
            )]
        for item in templates:
            item["pending_count"] = int(item.get("pending_count") or 0)
            item["rejected_count"] = int(item.get("rejected_count") or 0)
        return {
            "project": _row_to_dict(project),
            "templates": templates,
            "versions": versions,
            "promotions": promotions,
            "proposed_count": sum(1 for row in versions if row["status"] == "proposed"),
            "approved_count": sum(1 for row in versions if row["status"] == "approved"),
            "active_count": sum(1 for row in versions if row["status"] == "active"),
        }

    def version_detail(self, project_slug: str, version_key: str) -> dict[str, Any]:
        self.versions.sync_project(project_slug)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            version = self._get_version(conn, project_id=project["id"], version_key=version_key)
            active = conn.execute(
                """
                SELECT * FROM prompt_template_versions
                WHERE project_id = ? AND template_key = ? AND status = 'active'
                ORDER BY version_number DESC LIMIT 1
                """,
                (project["id"], version["template_key"]),
            ).fetchone()
            all_versions = [dict(row) for row in conn.execute(
                """
                SELECT version_key, version_number, status, source, summary, created_at
                FROM prompt_template_versions
                WHERE project_id = ? AND template_key = ?
                ORDER BY version_number DESC
                """,
                (project["id"], version["template_key"]),
            )]
            promotions = [dict(row) for row in conn.execute(
                """
                SELECT request_key, lab_type, case_key, run_key, status, proposal_markdown_path,
                       evidence_json_path, notes, applied_version_key, created_at
                FROM lab_promotion_requests
                WHERE project_id = ? AND (template_key = ? OR applied_version_key = ?)
                ORDER BY created_at DESC, id DESC
                """,
                (project["id"], version["template_key"], version_key),
            )]
        selected_markdown = self._read_version_markdown(version)
        active_markdown = self._read_version_markdown(active) if active is not None else ""
        sections = parse_markdown_sections(selected_markdown)
        evidence = self._load_evidence(promotions)
        return {
            "project": _row_to_dict(project),
            "version": _row_to_dict(version),
            "active_version": _row_to_dict(active),
            "all_versions": all_versions,
            "promotions": promotions,
            "evidence": evidence,
            "selected_markdown": selected_markdown,
            "active_markdown": active_markdown,
            "diff_lines": [line.to_dict() for line in _unified_diff(active_markdown, selected_markdown)],
            "sections": {
                "title": sections.section("title"),
                "task": sections.section("task"),
                "model_role": sections.section("model_role"),
                "instructions": sections.section("instructions"),
                "output_contract": sections.section("output_contract"),
            },
            "editable": str(version["status"]) in self.EDITABLE_STATUSES,
        }

    def create_manual_proposal(self, project_slug: str, *, template_key: str, summary: str = "") -> dict[str, Any]:
        active_markdown = self.versions.get_active_template_markdown(project_slug, template_key)
        proposal = self.versions.create_version(
            project_slug,
            template_key=template_key,
            markdown=active_markdown,
            source="manual_studio",
            summary=summary or "Manual Prompt Template Studio proposal.",
            source_target_type="prompt_template",
            source_target_id=template_key,
            activate=False,
        )
        return proposal.to_dict()

    def update_version_markdown(self, project_slug: str, version_key: str, *, markdown: str, summary: str = "") -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            version = self._get_version(conn, project_id=project["id"], version_key=version_key)
            if version["status"] not in self.EDITABLE_STATUSES:
                raise ValueError("Only proposed or approved prompt template versions can be edited in the studio.")
            self.versions._validate_template_markdown(markdown, template_key=version["template_key"])
            path = self.asset_store.safe_resolve(version["markdown_path"])
            self.asset_store.write_text(path, markdown.rstrip() + "\n")
            new_status = "proposed" if version["status"] == "approved" else version["status"]
            conn.execute(
                "UPDATE prompt_template_versions SET status = ?, summary = CASE WHEN ? != '' THEN ? ELSE summary END WHERE id = ?",
                (new_status, summary, summary, version["id"]),
            )
            return {"project_slug": project_slug, "version_key": version_key, "status": new_status, "markdown_path": version["markdown_path"]}

    def _get_version(self, conn: Connection, *, project_id: int, version_key: str) -> Row:
        row = conn.execute(
            "SELECT * FROM prompt_template_versions WHERE project_id = ? AND version_key = ?",
            (project_id, version_key),
        ).fetchone()
        if row is None:
            raise KeyError(f"Prompt template version not found: {version_key}")
        return row

    def _read_version_markdown(self, row: Row | None) -> str:
        if row is None:
            return ""
        path = self.asset_store.safe_resolve(row["markdown_path"])
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _load_evidence(self, promotions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for request in promotions:
            path_value = str(request.get("evidence_json_path") or "")
            if not path_value:
                continue
            try:
                path = self.asset_store.safe_resolve(path_value)
                payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (ValueError, OSError, json.JSONDecodeError):
                payload = {"error": "Could not load evidence file."}
            evidence.append({"request_key": request.get("request_key"), "payload": payload})
        return evidence


def _row_to_dict(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _unified_diff(active_markdown: str, selected_markdown: str) -> list[DiffLine]:
    if not active_markdown and not selected_markdown:
        return []
    lines = difflib.unified_diff(
        active_markdown.splitlines(),
        selected_markdown.splitlines(),
        fromfile="active",
        tofile="selected",
        lineterm="",
        n=3,
    )
    result: list[DiffLine] = []
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            kind = "meta"
        elif line.startswith("@@"):
            kind = "hunk"
        elif line.startswith("+"):
            kind = "add"
        elif line.startswith("-"):
            kind = "remove"
        else:
            kind = "context"
        result.append(DiffLine(kind=kind, text=line))
    return result
