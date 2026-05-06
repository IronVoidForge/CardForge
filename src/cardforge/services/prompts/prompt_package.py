from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.llm.markdown_sections import parse_bullet_key_values, parse_markdown_sections
from cardforge.services.projects.project_service import ProjectService


@dataclass(frozen=True)
class PromptTemplate:
    template_key: str
    title: str
    task: str
    model_role: str
    inputs_markdown: str
    instructions: str
    output_contract: str
    packet_shape: str
    sources: str
    path: Path

    @property
    def system_template(self) -> str:
        parts = [self.model_role, "", "OUTPUT CONTRACT:", self.output_contract, "", "PACKET SHAPE:", self.packet_shape]
        return "\n".join(part for part in parts if str(part).strip()).strip()

    @property
    def user_template(self) -> str:
        parts = ["INPUTS:", self.inputs_markdown, "", "INSTRUCTIONS:", self.instructions, "", "SOURCES:", self.sources]
        return "\n".join(part for part in parts if str(part).strip()).strip()


@dataclass(frozen=True)
class RenderedPromptPackage:
    package_key: str
    task_type: str
    template_key: str
    system_prompt: str
    user_prompt: str
    package_markdown: str
    package_markdown_path: str
    system_prompt_path: str
    user_prompt_path: str
    inputs: dict[str, Any]
    output_contract: dict[str, Any]


class PromptTemplateService:
    """Loads markdown prompt templates and renders reproducible prompt packages.

    The markdown format is intentionally human-readable and flexible. It uses the
    same parser style as the LLM packet salvage path: headings are normalized,
    inputs can be `- key: value`, and missing optional sections become empty
    strings instead of crashing the pipeline.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)

    def list_templates(self, project_slug: str) -> list[dict[str, Any]]:
        root = self.asset_store.project_root(project_slug) / "prompt_templates"
        items: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.md")):
            if path.name == "CARDFORGE_PROMPT_FORMAT.md":
                continue
            template = self.load_template(project_slug, path.stem)
            items.append({"template_key": template.template_key, "title": template.title, "task": template.task, "path": self.asset_store.relative_to_workspace(path)})
        return items

    def load_template(self, project_slug: str, template_key: str) -> PromptTemplate:
        path = self.asset_store.project_root(project_slug) / "prompt_templates" / f"{template_key}.md"
        if not path.exists():
            raise KeyError(f"Prompt template not found: {template_key}")
        text = path.read_text(encoding="utf-8")
        doc = parse_markdown_sections(text)
        title = doc.section("title") or template_key
        task = doc.section("task") or template_key
        return PromptTemplate(
            template_key=template_key,
            title=title.strip(),
            task=task.strip(),
            model_role=doc.section("model_role"),
            inputs_markdown=doc.section("inputs"),
            instructions=doc.section("instructions"),
            output_contract=doc.section("output_contract"),
            packet_shape=doc.section("packet_shape"),
            sources=doc.section("sources"),
            path=path,
        )

    def render_package(
        self,
        project_slug: str,
        *,
        template_key: str,
        context: dict[str, Any],
        task_type: str | None = None,
        set_id: int | None = None,
        card_id: int | None = None,
        batch_id: int | None = None,
        conn: Connection | None = None,
    ) -> RenderedPromptPackage:
        template = self.load_template(project_slug, template_key)
        rendered_context = {key: self._stringify(value) for key, value in context.items()}
        system_prompt = self._safe_format(template.system_template, rendered_context)
        user_prompt = self._safe_format(template.user_template, rendered_context)
        task = task_type or template.task
        package_markdown = self._package_markdown(template, system_prompt=system_prompt, user_prompt=user_prompt, context=context)

        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            package_key = next_key(conn, "prompt_packages", "package_key", "PROMPT", where="project_id = ?", params=(project["id"],))
            package_root = self.asset_store.project_root(project_slug) / "prompt_packages" / package_key
            package_path = package_root / "prompt_package.md"
            system_path = package_root / "system_prompt.md"
            user_path = package_root / "user_prompt.md"
            self.asset_store.write_text(package_path, package_markdown)
            self.asset_store.write_text(system_path, system_prompt + "\n")
            self.asset_store.write_text(user_path, user_prompt + "\n")
            contract = {
                "task": task,
                "template_key": template_key,
                "packet_required": True,
                "fallback_parsers": ["packet", "json", "markdown_table", "heading_blocks"],
            }
            conn.execute(
                """
                INSERT INTO prompt_packages(
                    project_id, set_id, card_id, batch_id, package_key, task_type, template_key,
                    package_markdown_path, system_prompt_path, user_prompt_path, input_payload_json, output_contract_json, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rendered')
                """,
                (
                    project["id"],
                    set_id,
                    card_id,
                    batch_id,
                    package_key,
                    task,
                    template_key,
                    self.asset_store.relative_to_workspace(package_path),
                    self.asset_store.relative_to_workspace(system_path),
                    self.asset_store.relative_to_workspace(user_path),
                    json.dumps(context, ensure_ascii=False, default=str),
                    json.dumps(contract, ensure_ascii=False),
                ),
            )
            if close:
                conn.commit()
            return RenderedPromptPackage(
                package_key=package_key,
                task_type=task,
                template_key=template_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                package_markdown=package_markdown,
                package_markdown_path=self.asset_store.relative_to_workspace(package_path),
                system_prompt_path=self.asset_store.relative_to_workspace(system_path),
                user_prompt_path=self.asset_store.relative_to_workspace(user_path),
                inputs=context,
                output_contract=contract,
            )
        finally:
            if close:
                conn.close()

    def parse_inputs_from_template(self, project_slug: str, template_key: str) -> dict[str, str]:
        template = self.load_template(project_slug, template_key)
        return parse_bullet_key_values(template.inputs_markdown)

    def _package_markdown(self, template: PromptTemplate, *, system_prompt: str, user_prompt: str, context: dict[str, Any]) -> str:
        return "\n".join(
            [
                "# Title",
                template.title,
                "",
                "# ID",
                template.template_key,
                "",
                "# Task",
                template.task,
                "",
                "# Rendered System Prompt",
                system_prompt,
                "",
                "# Rendered User Prompt",
                user_prompt,
                "",
                "# Input Payload",
                "```json",
                json.dumps(context, indent=2, ensure_ascii=False, default=str),
                "```",
                "",
            ]
        )

    def _safe_format(self, template: str, context: dict[str, str]) -> str:
        class SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        return str(template or "").format_map(SafeDict(context)).strip()

    def _stringify(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value or "")
