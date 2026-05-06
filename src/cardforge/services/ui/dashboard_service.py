from __future__ import annotations

import json
from sqlite3 import Row
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.status.status_service import StatusService


def _row_to_dict(row: Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return default


class UIDashboardService:
    """Read-only UI view-model queries.

    The UI should not contain SQL joins or artifact-location rules.  This service
    returns small dictionaries that are easy for Jinja templates and tests to use.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.status = StatusService(self.db)
        self.asset_store = AssetStore(self.db.settings)

    def project_overview(self, project_slug: str) -> dict[str, Any]:
        status = self.status.project_status(project_slug)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            project_id = project["id"]
            sets = [self._set_summary(conn, row) for row in conn.execute(
                "SELECT * FROM sets WHERE project_id = ? ORDER BY set_code", (project_id,)
            )]
            recent_cards = [self._card_summary(conn, row) for row in conn.execute(
                """
                SELECT c.* FROM cards c
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ?
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT 12
                """,
                (project_id,),
            )]
            open_reviews = [self._review_summary(row) for row in conn.execute(
                "SELECT * FROM review_items WHERE project_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 8",
                (project_id,),
            )]
            recent_batches = [self._batch_summary(conn, row) for row in conn.execute(
                """
                SELECT b.* FROM card_batches b
                JOIN sets s ON s.id = b.set_id
                WHERE s.project_id = ?
                ORDER BY b.created_at DESC, b.id DESC
                LIMIT 8
                """,
                (project_id,),
            )]
        return {
            "status": status,
            "sets": sets,
            "recent_cards": recent_cards,
            "open_reviews": open_reviews,
            "recent_batches": recent_batches,
        }

    def set_detail(self, project_slug: str, set_code: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_row = conn.execute(
                "SELECT * FROM sets WHERE project_id = ? AND set_code = ?", (project["id"], set_code)
            ).fetchone()
            if set_row is None:
                raise KeyError(f"Set not found: {set_code}")
            cards = [self._card_summary(conn, row) for row in conn.execute(
                "SELECT * FROM cards WHERE set_id = ? ORDER BY card_key", (set_row["id"],)
            )]
            batches = [self._batch_summary(conn, row) for row in conn.execute(
                "SELECT * FROM card_batches WHERE set_id = ? ORDER BY batch_key DESC", (set_row["id"],)
            )]
            open_reviews = [self._review_summary(row) for row in conn.execute(
                "SELECT * FROM review_items WHERE set_id = ? AND status = 'open' ORDER BY created_at DESC",
                (set_row["id"],),
            )]
        return {
            "project": _row_to_dict(project),
            "set": _row_to_dict(set_row),
            "cards": cards,
            "batches": batches,
            "open_reviews": open_reviews,
            "counts": {
                "cards": len(cards),
                "batches": len(batches),
                "open_reviews": len(open_reviews),
                "locked_cards": sum(1 for card in cards if card["status"] == "locked"),
                "rendered_cards": sum(1 for card in cards if card["latest_render"]),
            },
        }

    def card_detail(self, project_slug: str, card_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = conn.execute(
                """
                SELECT c.*, s.set_code, s.name AS set_name FROM cards c
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND c.card_key = ?
                """,
                (project["id"], card_key),
            ).fetchone()
            if card is None:
                raise KeyError(f"Card not found: {card_key}")
            detail = self._card_summary(conn, card)
            versions = [dict(row) for row in conn.execute(
                "SELECT * FROM card_versions WHERE card_id = ? ORDER BY version_number DESC", (card["id"],)
            )]
            art_candidates = [self._art_summary(row) for row in conn.execute(
                "SELECT * FROM art_candidates WHERE card_id = ? ORDER BY updated_at DESC, id DESC", (card["id"],)
            )]
            renders = [self._render_summary(row) for row in conn.execute(
                "SELECT * FROM renders WHERE card_id = ? ORDER BY created_at DESC, id DESC", (card["id"],)
            )]
            auto_reviews = [self._auto_review_summary(row) for row in conn.execute(
                "SELECT * FROM auto_reviews WHERE card_id = ? ORDER BY created_at DESC, id DESC LIMIT 10", (card["id"],)
            )]
            related_reviews = [self._review_summary(row) for row in conn.execute(
                """
                SELECT * FROM review_items
                WHERE project_id = ?
                  AND status = 'open'
                  AND (
                    (target_type = 'card' AND target_id = ?)
                    OR (metadata_json LIKE ?)
                  )
                ORDER BY created_at DESC
                """,
                (project["id"], card_key, f'%"card_key": "{card_key}"%'),
            )]
        return {
            "project": _row_to_dict(project),
            "card": detail,
            "versions": versions,
            "art_candidates": art_candidates,
            "renders": renders,
            "auto_reviews": auto_reviews,
            "open_reviews": related_reviews,
        }

    def batch_detail(self, project_slug: str, batch_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            batch = conn.execute(
                """
                SELECT b.*, s.set_code, s.name AS set_name FROM card_batches b
                JOIN sets s ON s.id = b.set_id
                WHERE s.project_id = ? AND b.batch_key = ?
                """,
                (project["id"], batch_key),
            ).fetchone()
            if batch is None:
                raise KeyError(f"Batch not found: {batch_key}")
            cards = [self._card_summary(conn, row) for row in conn.execute(
                "SELECT * FROM cards WHERE batch_id = ? ORDER BY card_key", (batch["id"],)
            )]
            reviews = [self._review_summary(row) for row in conn.execute(
                "SELECT * FROM review_items WHERE target_type = 'batch' AND target_id = ? ORDER BY created_at DESC",
                (batch_key,),
            )]
            batch_summary = self._batch_summary(conn, batch)
        return {
            "project": _row_to_dict(project),
            "batch": batch_summary,
            "cards": cards,
            "reviews": reviews,
        }

    def review_queue(self, project_slug: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            rows = list(conn.execute(
                "SELECT * FROM review_items WHERE project_id = ? ORDER BY status = 'open' DESC, created_at DESC",
                (project["id"],),
            ))
        return {
            "project": _row_to_dict(project),
            "reviews": [self._review_summary(row) for row in rows],
            "open_count": sum(1 for row in rows if row["status"] == "open"),
        }

    def template_library(self, project_slug: str) -> dict[str, Any]:
        from cardforge.services.templates.template_service import TemplateService

        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
        templates = TemplateService(self.db).list_templates(project_slug)
        return {
            "project": _row_to_dict(project),
            "templates": templates,
            "front_count": sum(1 for item in templates if item["template_type"] == "front"),
            "back_count": sum(1 for item in templates if item["template_type"] == "back"),
        }

    def template_detail(self, project_slug: str, template_key: str) -> dict[str, Any]:
        from cardforge.services.templates.template_service import TemplateService

        service = TemplateService(self.db)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = service.get_template_row(project_slug, template_key, conn=conn)
        summary = {key: row[key] for key in row.keys()}
        template = _json_loads(row["template_json"], {})
        return {
            "project": _row_to_dict(project),
            "template": summary,
            "template_json": json.dumps(template, indent=2, ensure_ascii=False),
            "layer_count": len(template.get("layers", [])) if isinstance(template.get("layers"), list) else 0,
        }




    def lab_dashboard(self, project_slug: str) -> dict[str, Any]:
        from cardforge.services.prompts.prompt_template_versioning import PromptTemplateVersionService

        PromptTemplateVersionService(self.db).sync_project(project_slug)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            prompt_cases = [self._prompt_lab_case_summary(row) for row in conn.execute(
                "SELECT * FROM prompt_lab_cases WHERE project_id = ? ORDER BY id DESC", (project["id"],)
            )]
            image_cases = [self._image_lab_case_summary(row) for row in conn.execute(
                "SELECT * FROM image_lab_cases WHERE project_id = ? ORDER BY id DESC", (project["id"],)
            )]
            cards = [self._card_summary(conn, row) for row in conn.execute(
                """
                SELECT c.* FROM cards c
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ?
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT 50
                """,
                (project["id"],),
            )]
            templates = [dict(row) for row in conn.execute(
                "SELECT template_key, name, task_type FROM prompt_templates WHERE project_id = ? ORDER BY template_key",
                (project["id"],),
            )]
            prompt_versions = [dict(row) for row in conn.execute(
                """
                SELECT template_key, version_key, version_number, status, source, summary, markdown_path
                FROM prompt_template_versions
                WHERE project_id = ?
                ORDER BY template_key, version_number DESC
                """,
                (project["id"],),
            )]
            promotion_requests = [self._lab_promotion_summary(row) for row in conn.execute(
                "SELECT * FROM lab_promotion_requests WHERE project_id = ? ORDER BY created_at DESC, id DESC",
                (project["id"],),
            )]
        return {
            "project": _row_to_dict(project),
            "prompt_cases": prompt_cases,
            "image_cases": image_cases,
            "cards": cards,
            "prompt_templates": templates,
            "prompt_versions": prompt_versions,
            "promotion_requests": promotion_requests,
            "open_prompt_cases": sum(1 for item in prompt_cases if item["status"] == "open"),
            "open_image_cases": sum(1 for item in image_cases if item["status"] == "open"),
            "open_promotions": sum(1 for item in promotion_requests if item["status"] == "requested"),
        }

    def integration_status(self, project_slug: str) -> dict[str, Any]:
        from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService

        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            comfy_jobs = [self._comfy_job_summary(row) for row in conn.execute(
                """
                SELECT cj.*, cw.workflow_key FROM comfy_jobs cj
                LEFT JOIN comfy_workflows cw ON cw.id = cj.workflow_id
                ORDER BY cj.id DESC LIMIT 20
                """
            )]
        workflows = WorkflowRegistryService(self.db).list_workflows()
        settings = self.db.settings
        return {
            "project": _row_to_dict(project),
            "settings": {
                "lmstudio_base_url": settings.lmstudio_base_url,
                "lmstudio_model": settings.lmstudio_model,
                "lmstudio_review_model": settings.lmstudio_review_model,
                "comfy_base_url": settings.comfy_base_url,
                "comfy_input_dir": str(settings.comfy_input_dir),
                "comfy_output_dir": str(settings.comfy_output_dir),
            },
            "workflows": workflows,
            "comfy_jobs": comfy_jobs,
        }

    def job_queue(self, project_slug: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            rows = list(
                conn.execute(
                    """
                    SELECT * FROM generation_jobs
                    WHERE project_id = ?
                    ORDER BY status = 'pending' DESC, status = 'running' DESC, created_at DESC, id DESC
                    LIMIT 100
                    """,
                    (project["id"],),
                )
            )
            recent_events = list(
                conn.execute(
                    """
                    SELECT * FROM audit_events
                    WHERE project_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                    """,
                    (project["id"],),
                )
            )
        return {
            "project": _row_to_dict(project),
            "jobs": [self._job_summary(row) for row in rows],
            "events": [self._audit_summary(row) for row in recent_events],
            "pending_count": sum(1 for row in rows if row["status"] == "pending"),
            "running_count": sum(1 for row in rows if row["status"] == "running"),
            "failed_count": sum(1 for row in rows if row["status"] == "failed"),
        }


    def _lab_promotion_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        summary["has_evidence"] = bool(str(summary.get("evidence_json_path") or ""))
        summary["has_proposal"] = bool(str(summary.get("proposal_markdown_path") or ""))
        return summary

    def _prompt_lab_case_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        with self.db.connection() as conn:
            summary["run_count"] = conn.execute("SELECT COUNT(*) AS n FROM prompt_lab_runs WHERE case_id = ?", (row["id"],)).fetchone()["n"]
        return summary

    def _image_lab_case_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        with self.db.connection() as conn:
            summary["attempt_count"] = conn.execute("SELECT COUNT(*) AS n FROM image_lab_attempts WHERE case_id = ?", (row["id"],)).fetchone()["n"]
        return summary

    def _set_summary(self, conn: Any, row: Row) -> dict[str, Any]:
        card_count = conn.execute("SELECT COUNT(*) AS n FROM cards WHERE set_id = ?", (row["id"],)).fetchone()["n"]
        batch_count = conn.execute("SELECT COUNT(*) AS n FROM card_batches WHERE set_id = ?", (row["id"],)).fetchone()["n"]
        open_reviews = conn.execute("SELECT COUNT(*) AS n FROM review_items WHERE set_id = ? AND status = 'open'", (row["id"],)).fetchone()["n"]
        summary = _row_to_dict(row) or {}
        summary.update({"card_count": card_count, "batch_count": batch_count, "open_reviews": open_reviews})
        return summary

    def _batch_summary(self, conn: Any, row: Row) -> dict[str, Any]:
        card_count = conn.execute("SELECT COUNT(*) AS n FROM cards WHERE batch_id = ?", (row["id"],)).fetchone()["n"]
        summary = _row_to_dict(row) or {}
        summary["card_count"] = card_count
        summary["request_json"] = _json_loads(row["request_json"], {})
        summary["validation_summary"] = _json_loads(row["validation_summary_json"], {})
        summary["balance_summary"] = _json_loads(row["balance_summary_json"], {})
        return summary

    def _card_summary(self, conn: Any, row: Row) -> dict[str, Any]:
        latest_render = conn.execute(
            "SELECT * FROM renders WHERE card_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (row["id"],)
        ).fetchone()
        locked_art = conn.execute(
            "SELECT * FROM art_candidates WHERE card_id = ? AND status = 'locked' ORDER BY updated_at DESC, id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        auto_review = conn.execute(
            "SELECT * FROM auto_reviews WHERE card_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (row["id"],)
        ).fetchone()
        summary = _row_to_dict(row) or {}
        summary["cost"] = _json_loads(row["cost_json"], {})
        summary["stats"] = _json_loads(row["stats_json"], {})
        summary["keywords"] = _json_loads(row["keywords_json"], [])
        summary["latest_render"] = self._render_summary(latest_render) if latest_render else None
        summary["locked_art"] = self._art_summary(locked_art) if locked_art else None
        summary["latest_auto_review"] = self._auto_review_summary(auto_review) if auto_review else None
        return summary

    def _review_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        summary["metadata"] = _json_loads(row["metadata_json"], {})
        return summary

    def _render_summary(self, row: Row | None) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        if summary:
            summary["layout_report"] = _json_loads(row["layout_report_json"], {})
        return summary

    def _art_summary(self, row: Row | None) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        if summary:
            summary["settings"] = _json_loads(row["settings_json"], {})
            summary["score"] = _json_loads(row["score_json"], {})
        return summary

    def _auto_review_summary(self, row: Row | None) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        if summary:
            summary["findings"] = _json_loads(row["findings_json"], [])
            summary["recommendations"] = _json_loads(row["recommendations_json"], [])
        return summary


    def _comfy_job_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        summary["settings"] = _json_loads(row["settings_json"], {})
        return summary

    def _job_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        summary["payload"] = _json_loads(row["payload_json"], {})
        summary["result"] = _json_loads(row["result_json"], {})
        return summary

    def _audit_summary(self, row: Row) -> dict[str, Any]:
        summary = _row_to_dict(row) or {}
        summary["payload"] = _json_loads(row["payload_json"], {})
        return summary
