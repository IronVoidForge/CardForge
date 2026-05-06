from __future__ import annotations

import json
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.templates.template_defaults import DEFAULT_TEMPLATE_REGISTRY, default_back_template, default_front_template
from cardforge.services.templates.template_models import TemplateBox, box_for_layer, layer_by_id, rgb


class TemplateValidationError(ValueError):
    """Raised when a card render template is missing required structure."""


class TemplateService:
    """Project-scoped template registry and preview service.

    Templates are stored as human-readable JSON in each project folder and synced
    into SQLite for searching/status queries.  The renderer reads through this
    service so old minimal registries can be hydrated into the full v2 shape.
    """

    REQUIRED_FRONT_LAYERS = {"title", "cost", "art", "type_line", "rules_text", "flavor_text", "stats"}
    REQUIRED_BACK_LAYERS = {"outer_frame", "inner_frame", "emblem", "title", "subtitle"}

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)

    def sync_project_templates(self, project_slug: str, *, conn: Connection | None = None) -> dict[str, Any]:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            registry = self.load_registry(project_slug)
            templates = registry.get("templates", {})
            synced: list[str] = []
            for template_key, template in sorted(templates.items()):
                hydrated = self.hydrate_template(template_key, template)
                self.validate_template_dict(hydrated)
                canvas = hydrated.get("canvas", {})
                conn.execute(
                    """
                    INSERT INTO templates(project_id, template_key, name, template_type, card_type, canvas_width, canvas_height, template_json, status)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    ON CONFLICT(project_id, template_key) DO UPDATE SET
                      name=excluded.name,
                      template_type=excluded.template_type,
                      card_type=excluded.card_type,
                      canvas_width=excluded.canvas_width,
                      canvas_height=excluded.canvas_height,
                      template_json=excluded.template_json,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        project["id"],
                        template_key,
                        str(hydrated.get("name") or template_key),
                        str(hydrated.get("template_type") or "front"),
                        str(hydrated.get("card_type") or "any"),
                        int(canvas.get("width", 750)),
                        int(canvas.get("height", 1050)),
                        json.dumps(hydrated, ensure_ascii=False),
                    ),
                )
                synced.append(template_key)
            if close:
                conn.commit()
            return {"project_slug": project_slug, "synced_count": len(synced), "templates": synced}
        finally:
            if close:
                conn.close()

    def list_templates(self, project_slug: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            self.sync_project_templates(project_slug, conn=conn)
            project = self.projects.get_project(project_slug, conn=conn)
            rows = conn.execute(
                "SELECT * FROM templates WHERE project_id = ? ORDER BY template_type, card_type, template_key",
                (project["id"],),
            ).fetchall()
            return [self._row_to_template_summary(row) for row in rows]

    def get_template_row(self, project_slug: str, template_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            self.sync_project_templates(project_slug, conn=conn)
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                "SELECT * FROM templates WHERE project_id = ? AND template_key = ?",
                (project["id"], template_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Template not found: {template_key}")
            return row
        finally:
            if close:
                conn.close()

    def get_template(self, project_slug: str, template_key: str, *, conn: Connection | None = None) -> dict[str, Any]:
        row = self.get_template_row(project_slug, template_key, conn=conn)
        return json.loads(row["template_json"] or "{}")

    def update_template(self, project_slug: str, template_key: str, template_json: str | dict[str, Any]) -> dict[str, Any]:
        template = json.loads(template_json) if isinstance(template_json, str) else dict(template_json)
        template["template_key"] = template_key
        self.validate_template_dict(template)
        registry = self.load_registry(project_slug)
        registry.setdefault("templates", {})[template_key] = template
        self._write_registry(project_slug, registry)
        self.sync_project_templates(project_slug)
        return {"project_slug": project_slug, "template_key": template_key, "status": "updated"}

    def validate_template(self, project_slug: str, template_key: str) -> dict[str, Any]:
        template = self.get_template(project_slug, template_key)
        self.validate_template_dict(template)
        return {"template_key": template_key, "valid": True, "required_layers_present": True}

    def validate_template_dict(self, template: dict[str, Any]) -> None:
        template_type = str(template.get("template_type") or "").strip()
        if template_type not in {"front", "back"}:
            raise TemplateValidationError("Template must declare template_type 'front' or 'back'.")
        canvas = template.get("canvas")
        if not isinstance(canvas, dict) or int(canvas.get("width", 0)) <= 0 or int(canvas.get("height", 0)) <= 0:
            raise TemplateValidationError("Template must include positive canvas.width and canvas.height.")
        layers = template.get("layers")
        if not isinstance(layers, list) or not layers:
            raise TemplateValidationError("Template must include a non-empty layers list.")
        layer_ids = {str(layer.get("id") or "") for layer in layers if isinstance(layer, dict)}
        required = self.REQUIRED_BACK_LAYERS if template_type == "back" else self.REQUIRED_FRONT_LAYERS
        missing = sorted(required - layer_ids)
        if missing:
            raise TemplateValidationError(f"Template is missing required layer(s): {', '.join(missing)}")
        for layer in layers:
            if not isinstance(layer, dict):
                raise TemplateValidationError("Every template layer must be an object.")
            if not str(layer.get("id") or "").strip():
                raise TemplateValidationError("Every template layer must have an id.")
            if "box" in layer:
                box = TemplateBox.from_value(layer["box"])
                if box.width <= 0 or box.height <= 0:
                    raise TemplateValidationError(f"Layer {layer.get('id')} has a non-positive box.")

    def render_preview(self, project_slug: str, template_key: str) -> dict[str, Any]:
        template = self.get_template(project_slug, template_key)
        canvas = template.get("canvas", {})
        width, height = int(canvas.get("width", 750)), int(canvas.get("height", 1050))
        colors = template.get("colors", {}) if isinstance(template.get("colors"), dict) else {}
        img = Image.new("RGB", (width, height), rgb(colors.get("background"), (236, 232, 220)))
        draw = ImageDraw.Draw(img)
        for layer in template.get("layers", []):
            if not isinstance(layer, dict) or "box" not in layer:
                continue
            box = TemplateBox.from_value(layer["box"])
            color = rgb(colors.get("frame"), (70, 60, 82)) if layer.get("type") != "image_slot" else rgb(colors.get("art_placeholder"), (135, 125, 145))
            if layer.get("type") in {"rounded_rect", "image_slot", "rich_text", "text", "cost", "stats"}:
                draw.rectangle(box.as_tuple(), outline=color, width=3)
                self._label(draw, str(layer.get("id", "layer")), box)
            elif layer.get("type") == "ellipse":
                draw.ellipse(box.as_tuple(), outline=color, width=3)
                self._label(draw, str(layer.get("id", "layer")), box)
        preview_path = self.asset_store.project_root(project_slug) / "templates" / f"{template_key}_preview.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(preview_path)
        rel = self.asset_store.relative_to_workspace(preview_path)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            conn.execute(
                "UPDATE templates SET preview_path = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ? AND template_key = ?",
                (rel, project["id"], template_key),
            )
        return {"template_key": template_key, "preview_path": rel}

    def load_registry(self, project_slug: str) -> dict[str, Any]:
        path = self._registry_path(project_slug)
        if not path.exists():
            self._write_registry(project_slug, DEFAULT_TEMPLATE_REGISTRY)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = DEFAULT_TEMPLATE_REGISTRY
        templates = payload.setdefault("templates", {})
        for key, default in DEFAULT_TEMPLATE_REGISTRY["templates"].items():
            templates.setdefault(key, default)
        payload.setdefault("schema_version", "2026-05-template-registry-v2")
        return payload

    def hydrate_template(self, template_key: str, template: dict[str, Any]) -> dict[str, Any]:
        if "canvas" in template and "layers" in template:
            hydrated = dict(template)
            hydrated.setdefault("template_key", template_key)
            hydrated.setdefault("name", template_key)
            return hydrated
        template_type = str(template.get("template_type") or "front")
        card_type = str(template.get("card_type") or "creature")
        if template_type == "back":
            return default_back_template()
        return default_front_template(template_key, card_type)

    def _registry_path(self, project_slug: str) -> Path:
        return self.asset_store.project_root(project_slug) / "template_registry.json"

    def _write_registry(self, project_slug: str, registry: dict[str, Any]) -> None:
        path = self._registry_path(project_slug)
        self.asset_store.write_json(path, registry)

    def _row_to_template_summary(self, row: Row) -> dict[str, Any]:
        payload = {key: row[key] for key in row.keys()}
        try:
            payload["template"] = json.loads(row["template_json"] or "{}")
        except json.JSONDecodeError:
            payload["template"] = {}
        return payload

    def _label(self, draw: ImageDraw.ImageDraw, text: str, box: TemplateBox) -> None:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        draw.text((box.left + 6, box.top + 5), text, font=font, fill=(28, 24, 35))
