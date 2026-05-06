from __future__ import annotations

import json
from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.llm.markdown_sections import parse_markdown_sections
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.prompts.prompt_package import PromptTemplateService


@dataclass(frozen=True)
class PromptTemplateVersion:
    template_key: str
    version_key: str
    version_number: int
    markdown_path: str
    status: str
    source: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_key": self.template_key,
            "version_key": self.version_key,
            "version_number": self.version_number,
            "markdown_path": self.markdown_path,
            "status": self.status,
            "source": self.source,
            "summary": self.summary,
        }


class PromptTemplateVersionService:
    """Version-controlled prompt template operations."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.templates = PromptTemplateService(self.db)

    def sync_project(self, project_slug: str) -> dict[str, Any]:
        self.templates.sync_templates(project_slug)
        templates = self.templates.list_templates(project_slug)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            synced: list[dict[str, Any]] = []
            for item in templates:
                seeded = self._ensure_initial_version(
                    conn,
                    project_slug=project_slug,
                    project_id=project["id"],
                    template_key=item["template_key"],
                )
                synced.append({"template_key": item["template_key"], "seeded_initial_version": seeded})
            return {"project_slug": project_slug, "synced_count": len(synced), "templates": synced}

    def list_versions(self, project_slug: str, template_key: str | None = None) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            if template_key:
                rows = conn.execute(
                    """
                    SELECT * FROM prompt_template_versions
                    WHERE project_id = ? AND template_key = ?
                    ORDER BY template_key, version_number DESC
                    """,
                    (project["id"], template_key),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM prompt_template_versions
                    WHERE project_id = ?
                    ORDER BY template_key, version_number DESC
                    """,
                    (project["id"],),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    def get_active_template_markdown(self, project_slug: str, template_key: str) -> str:
        path = self.asset_store.project_root(project_slug) / "prompt_templates" / f"{template_key}.md"
        if not path.exists():
            raise KeyError(f"Prompt template not found: {template_key}")
        return path.read_text(encoding="utf-8")

    def create_version(
        self,
        project_slug: str,
        *,
        template_key: str,
        markdown: str,
        source: str,
        summary: str,
        source_target_type: str = "",
        source_target_id: str = "",
        activate: bool = False,
        conn: Connection | None = None,
    ) -> PromptTemplateVersion:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            self._validate_template_markdown(markdown, template_key=template_key)
            version_number = self._next_version_number(conn, project_id=project["id"], template_key=template_key)
            version_key = f"{template_key}_v{version_number:03d}"
            version_dir = self.asset_store.project_root(project_slug) / "prompt_templates" / "versions" / template_key
            version_path = version_dir / f"{version_key}.md"
            self.asset_store.write_text(version_path, markdown.rstrip() + "\n")
            status = "active" if activate else "proposed"
            conn.execute(
                """
                INSERT INTO prompt_template_versions(
                    project_id, template_key, version_number, version_key, source,
                    source_target_type, source_target_id, markdown_path, summary, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project["id"],
                    template_key,
                    version_number,
                    version_key,
                    source,
                    source_target_type,
                    source_target_id,
                    self.asset_store.relative_to_workspace(version_path),
                    summary,
                    status,
                ),
            )
            if activate:
                self._activate_version(
                    conn,
                    project_slug=project_slug,
                    project_id=project["id"],
                    template_key=template_key,
                    version_key=version_key,
                    markdown=markdown,
                )
            if close:
                conn.commit()
            return PromptTemplateVersion(
                template_key=template_key,
                version_key=version_key,
                version_number=version_number,
                markdown_path=self.asset_store.relative_to_workspace(version_path),
                status=status,
                source=source,
                summary=summary,
            )
        finally:
            if close:
                conn.close()

    def approve_version(self, project_slug: str, version_key: str, *, notes: str = "") -> dict[str, Any]:
        return self._set_version_status(project_slug, version_key, status="approved", notes=notes)

    def reject_version(self, project_slug: str, version_key: str, *, notes: str = "") -> dict[str, Any]:
        return self._set_version_status(project_slug, version_key, status="rejected", notes=notes)

    def activate_version(self, project_slug: str, version_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                "SELECT * FROM prompt_template_versions WHERE project_id = ? AND version_key = ?",
                (project["id"], version_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Prompt template version not found: {version_key}")
            if row["status"] not in {"approved", "active"}:
                raise ValueError("Prompt template version must be approved before activation.")
            markdown = self.asset_store.safe_resolve(row["markdown_path"]).read_text(encoding="utf-8")
            self._validate_template_markdown(markdown, template_key=row["template_key"])
            self._activate_version(
                conn,
                project_slug=project_slug,
                project_id=project["id"],
                template_key=row["template_key"],
                version_key=version_key,
                markdown=markdown,
            )
            return {"project_slug": project_slug, "template_key": row["template_key"], "version_key": version_key, "status": "active"}

    def _set_version_status(self, project_slug: str, version_key: str, *, status: str, notes: str) -> dict[str, Any]:
        if status not in {"approved", "rejected", "proposed"}:
            raise ValueError(f"Unsupported prompt template version status: {status}")
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                "SELECT * FROM prompt_template_versions WHERE project_id = ? AND version_key = ?",
                (project["id"], version_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Prompt template version not found: {version_key}")
            if row["status"] == "active" and status == "rejected":
                raise ValueError("Active prompt template versions cannot be rejected without activating a replacement.")
            conn.execute(
                "UPDATE prompt_template_versions SET status = ?, summary = CASE WHEN ? != '' THEN ? ELSE summary END WHERE id = ?",
                (status, notes, notes, row["id"]),
            )
            return {"project_slug": project_slug, "version_key": version_key, "status": status, "notes": notes}

    def _ensure_initial_version(self, conn: Connection, *, project_slug: str, project_id: int, template_key: str) -> bool:
        existing = conn.execute(
            "SELECT id FROM prompt_template_versions WHERE project_id = ? AND template_key = ? LIMIT 1",
            (project_id, template_key),
        ).fetchone()
        if existing is not None:
            return False
        markdown = self.get_active_template_markdown(project_slug, template_key)
        version_dir = self.asset_store.project_root(project_slug) / "prompt_templates" / "versions" / template_key
        version_key = f"{template_key}_v001"
        version_path = version_dir / f"{version_key}.md"
        self.asset_store.write_text(version_path, markdown.rstrip() + "\n")
        conn.execute(
            """
            INSERT INTO prompt_template_versions(
                project_id, template_key, version_number, version_key, source,
                markdown_path, summary, status
            ) VALUES(?, ?, 1, ?, 'scaffold', ?, 'Initial scaffolded prompt template.', 'active')
            """,
            (project_id, template_key, version_key, self.asset_store.relative_to_workspace(version_path)),
        )
        return True

    def _activate_version(
        self,
        conn: Connection,
        *,
        project_slug: str,
        project_id: int,
        template_key: str,
        version_key: str,
        markdown: str,
    ) -> None:
        conn.execute(
            "UPDATE prompt_template_versions SET status = 'superseded' WHERE project_id = ? AND template_key = ? AND status = 'active'",
            (project_id, template_key),
        )
        conn.execute(
            "UPDATE prompt_template_versions SET status = 'active' WHERE project_id = ? AND version_key = ?",
            (project_id, version_key),
        )
        active_path = self.asset_store.project_root(project_slug) / "prompt_templates" / f"{template_key}.md"
        self.asset_store.write_text(active_path, markdown.rstrip() + "\n")
        self.templates.sync_templates(project_slug, conn=conn)

    def _next_version_number(self, conn: Connection, *, project_id: int, template_key: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_n FROM prompt_template_versions WHERE project_id = ? AND template_key = ?",
            (project_id, template_key),
        ).fetchone()
        return int(row["next_n"])

    def _validate_template_markdown(self, markdown: str, *, template_key: str) -> None:
        doc = parse_markdown_sections(markdown)
        required = {
            "Title": doc.section("title"),
            "Task": doc.section("task"),
            "Model Role": doc.section("model_role"),
            "Instructions": doc.section("instructions"),
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Prompt template {template_key} is missing required section(s): {', '.join(missing)}")


def _row_to_dict(row: Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
