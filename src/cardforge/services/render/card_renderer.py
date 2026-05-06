from __future__ import annotations

import json
from pathlib import Path
from sqlite3 import Row
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cardforge.db.session import Database
from cardforge.domain.enums import CardStatus, RenderStatus
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.text_layout import TextLayoutEngine
from cardforge.services.review.review_service import ReviewService
from cardforge.services.templates.template_models import TemplateBox, box_for_layer, layer_by_id, rgb
from cardforge.services.templates.template_service import TemplateService


class CardRenderer:
    """Deterministic template-driven Pillow renderer for card fronts/backs.

    Image generators create illustration assets only.  This renderer owns all
    readable card text, frame composition, preview generation, layout reports,
    and review item creation.  Template JSON controls canvas size, layer boxes,
    colors, and font roles so card designs stay editable without code changes.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.text = TextLayoutEngine()
        self.art_candidates = ArtCandidateService(self.db)
        self.templates = TemplateService(self.db)

    def render_card(self, project_slug: str, card_key: str, *, placeholder_art: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            front_template_key = str(card["template_id"] or f"default_{card['card_type']}_front_v1")
            back_template_key = str(card["back_template_id"] or "default_card_back_v1")
            front_template_row = self.templates.get_template_row(project_slug, front_template_key, conn=conn)
            back_template_row = self.templates.get_template_row(project_slug, back_template_key, conn=conn)
            front_template = json.loads(front_template_row["template_json"] or "{}")
            back_template = json.loads(back_template_row["template_json"] or "{}")
            render_key = next_key(conn, "renders", "render_key", "RENDER", where="card_id = ?", params=(card["id"],))
            render_root = self.asset_store.project_root(project_slug) / "cards" / card_key / "renders"
            render_root.mkdir(parents=True, exist_ok=True)
            front_path = render_root / f"front_{render_key.lower()}.png"
            back_path = render_root / f"back_{render_key.lower()}.png"
            preview_path = render_root / f"preview_{render_key.lower()}.png"
            locked_art_path = None if placeholder_art else self.art_candidates.locked_art_path(project_slug, card_key)
            front_report = self._draw_front(
                card,
                front_path,
                template=front_template,
                placeholder_art=placeholder_art,
                art_path=locked_art_path,
            )
            back_report = self._draw_back(card, back_path, template=back_template, project_name=project["name"])
            self._draw_preview(front_path, back_path, preview_path)
            layout_report = {
                **front_report,
                "back_rendered": back_report["rendered"],
                "template_id": front_template_key,
                "back_template_id": back_template_key,
                "template_canvas": front_template.get("canvas", {}),
                "locked_art_used": bool(locked_art_path),
                "placeholder_art_used": bool(placeholder_art),
            }
            status = RenderStatus.RENDERED.value if layout_report["all_text_fit"] else RenderStatus.LAYOUT_WARNING.value
            conn.execute(
                """
                INSERT INTO renders(
                    card_id, card_version_id, art_candidate_id, template_id, render_key,
                    front_path, back_path, preview_path, layout_report_json, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card["id"],
                    card["current_version_id"],
                    self._locked_art_candidate_id(conn, card["id"]),
                    front_template_row["id"],
                    render_key,
                    self.asset_store.relative_to_workspace(front_path),
                    self.asset_store.relative_to_workspace(back_path),
                    self.asset_store.relative_to_workspace(preview_path),
                    json.dumps(layout_report),
                    status,
                ),
            )
            conn.execute(
                "UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (CardStatus.RENDERED.value, card["id"]),
            )
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=card["set_id"],
                target_type="render",
                target_id=render_key,
                review_type="render",
                title=f"Review render: {card['name']}",
                description="Rendered card front/back needs final visual review.",
                preview_path=self.asset_store.relative_to_workspace(preview_path),
                metadata={"card_key": card_key, "layout_report": layout_report},
                conn=conn,
            )
            return {
                "render_key": render_key,
                "front_path": self.asset_store.relative_to_workspace(front_path),
                "back_path": self.asset_store.relative_to_workspace(back_path),
                "preview_path": self.asset_store.relative_to_workspace(preview_path),
                "layout_report": layout_report,
                "status": status,
            }

    def _draw_front(
        self,
        card: Row,
        path: Path,
        *,
        template: dict[str, Any],
        placeholder_art: bool,
        art_path: Path | None = None,
    ) -> dict[str, Any]:
        canvas = template.get("canvas", {})
        width, height = int(canvas.get("width", 750)), int(canvas.get("height", 1050))
        colors = self._colors(template)
        img = Image.new("RGB", (width, height), colors["background"])
        draw = ImageDraw.Draw(img)
        self._draw_front_frame(draw, template, colors, width, height)
        self._draw_title_bar(draw, template, colors, card)
        self._draw_art_slot(img, draw, template, colors, art_path=art_path, placeholder_art=placeholder_art)
        self._draw_type_line(draw, template, colors, card)
        rules_fit = self._draw_rules_text(draw, template, colors, card)
        flavor_fit = self._draw_flavor_text(draw, template, colors, card)
        self._draw_stats(draw, template, colors, card)
        img.save(path)
        return {
            "rules_text_fit": rules_fit,
            "flavor_text_fit": flavor_fit,
            "all_text_fit": rules_fit and flavor_fit,
            "required_layers": self._front_layer_presence(template),
        }

    def _draw_front_frame(
        self,
        draw: ImageDraw.ImageDraw,
        template: dict[str, Any],
        colors: dict[str, tuple[int, int, int]],
        width: int,
        height: int,
    ) -> None:
        outer = box_for_layer(template, "outer_frame", (24, 24, width - 24, height - 24))
        inner = box_for_layer(template, "inner_frame", (46, 46, width - 46, height - 46))
        draw.rounded_rectangle(outer.as_tuple(), radius=int(layer_by_id(template, "outer_frame").get("radius", 34)), fill=colors["border"])
        draw.rounded_rectangle(inner.as_tuple(), radius=int(layer_by_id(template, "inner_frame").get("radius", 24)), fill=(221, 213, 196))
        for y in range(inner.top + 24, inner.bottom - 24, 42):
            draw.line((inner.left + 24, y, inner.right - 24, y), fill=(210, 200, 185), width=1)

    def _draw_title_bar(
        self, draw: ImageDraw.ImageDraw, template: dict[str, Any], colors: dict[str, tuple[int, int, int]], card: Row) -> None:
        title_bar = box_for_layer(template, "title_bar", (64, 64, 686, 150))
        title_box = box_for_layer(template, "title", (86, 82, 610, 142))
        cost_box = box_for_layer(template, "cost", (625, 78, 690, 143))
        draw.rounded_rectangle(title_bar.as_tuple(), radius=int(layer_by_id(template, "title_bar").get("radius", 14)), fill=colors["panel"], outline=colors["frame"], width=3)
        title_font = self._font_role(template, "title")
        title_font, title_lines, _ = self.text.fit_font_size(
            str(card["name"]),
            None,
            max_width=title_box.width,
            max_height=title_box.height,
            start_size=getattr(title_font, "size", 40),
            min_size=self._font_min(template, "title", 24),
            draw=draw,
        )
        draw.text((title_box.left, title_box.top + 4), title_lines[0] if title_lines else str(card["name"]), fill=colors["text"], font=title_font)
        cost = json.loads(card["cost_json"] or "{}")
        draw.ellipse(cost_box.as_tuple(), fill=(245, 245, 235), outline=colors["frame"], width=3)
        self._center_text(draw, str(cost.get("display", "")), cost_box.as_tuple(), self._font_role(template, "cost"), fill=colors["text"])

    def _draw_art_slot(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        template: dict[str, Any],
        colors: dict[str, tuple[int, int, int]],
        *,
        art_path: Path | None,
        placeholder_art: bool,
    ) -> None:
        art_box = box_for_layer(template, "art", (78, 170, 672, 520))
        draw.rectangle(art_box.as_tuple(), fill=colors["art_placeholder"], outline=colors["frame"], width=4)
        if art_path and art_path.exists():
            art = Image.open(art_path).convert("RGB")
            img.paste(self._cover_resize(art, art_box.width, art_box.height), (art_box.left, art_box.top))
            draw.rectangle(art_box.as_tuple(), outline=colors["frame"], width=4)
            return
        label = "PLACEHOLDER ART" if placeholder_art else "NO LOCKED ART"
        self._center_text(draw, label, art_box.as_tuple(), self._font(34), fill=(240, 235, 220))

    def _draw_type_line(self, draw: ImageDraw.ImageDraw, template: dict[str, Any], colors: dict[str, tuple[int, int, int]], card: Row) -> None:
        type_bar = box_for_layer(template, "type_bar", (78, 535, 672, 590))
        type_box = box_for_layer(template, "type_line", (96, 542, 650, 586))
        draw.rounded_rectangle(type_bar.as_tuple(), radius=int(layer_by_id(template, "type_bar").get("radius", 8)), fill=colors["panel"], outline=colors["frame"], width=3)
        text = str(card["type_line"] or card["card_type"]).title()
        font = self._font_role(template, "type_line")
        font, lines, _ = self.text.fit_font_size(text, None, max_width=type_box.width, max_height=type_box.height, start_size=getattr(font, "size", 28), min_size=self._font_min(template, "type_line", 18), draw=draw)
        draw.text((type_box.left, type_box.top + 3), lines[0] if lines else text, fill=colors["text"], font=font)

    def _draw_rules_text(self, draw: ImageDraw.ImageDraw, template: dict[str, Any], colors: dict[str, tuple[int, int, int]], card: Row) -> bool:
        panel_box = box_for_layer(template, "rules_panel", (78, 605, 672, 890))
        rules_box = box_for_layer(template, "rules_text", (92, 620, 658, 865))
        draw.rounded_rectangle(panel_box.as_tuple(), radius=int(layer_by_id(template, "rules_panel").get("radius", 10)), fill=(248, 246, 238), outline=colors["frame"], width=3)
        font = self._font_role(template, "rules")
        rules_font, rules_lines, rules_fit = self.text.fit_font_size(
            card["rules_text"],
            None,
            max_width=rules_box.width,
            max_height=rules_box.height,
            start_size=getattr(font, "size", 27),
            min_size=self._font_min(template, "rules", 17),
            draw=draw,
        )
        y = rules_box.top
        line_height = max(18, int(getattr(rules_font, "size", 22) * 1.18))
        for line in rules_lines[: int(layer_by_id(template, "rules_text").get("max_lines", 12))]:
            draw.text((rules_box.left, y), line, fill=colors["text"], font=rules_font)
            y += line_height
        return rules_fit

    def _draw_flavor_text(self, draw: ImageDraw.ImageDraw, template: dict[str, Any], colors: dict[str, tuple[int, int, int]], card: Row) -> bool:
        flavor = str(card["flavor_text"] or "").strip()
        if not flavor:
            return True
        flavor_box = box_for_layer(template, "flavor_text", (94, 905, 634, 980))
        font = self._font_role(template, "flavor")
        flavor_font, flavor_lines, flavor_fit = self.text.fit_font_size(
            flavor,
            None,
            max_width=flavor_box.width,
            max_height=flavor_box.height,
            start_size=getattr(font, "size", 21),
            min_size=self._font_min(template, "flavor", 15),
            draw=draw,
        )
        y = flavor_box.top
        line_height = max(16, int(getattr(flavor_font, "size", 18) * 1.2))
        for line in flavor_lines[: int(layer_by_id(template, "flavor_text").get("max_lines", 3))]:
            draw.text((flavor_box.left, y), line, fill=colors["muted_text"], font=flavor_font)
            y += line_height
        return flavor_fit

    def _draw_stats(self, draw: ImageDraw.ImageDraw, template: dict[str, Any], colors: dict[str, tuple[int, int, int]], card: Row) -> None:
        stats = json.loads(card["stats_json"] or "{}")
        if stats.get("attack") is None and stats.get("health") is None:
            return
        stats_box = box_for_layer(template, "stats", (560, 930, 680, 995))
        draw.rounded_rectangle(stats_box.as_tuple(), radius=16, fill=colors["panel"], outline=colors["frame"], width=4)
        self._center_text(draw, f"{stats.get('attack', '-')}/{stats.get('health', '-')}", stats_box.as_tuple(), self._font_role(template, "stats"), fill=colors["text"])

    def _draw_back(self, card: Row, path: Path, *, template: dict[str, Any], project_name: str) -> dict[str, Any]:
        canvas = template.get("canvas", {})
        width, height = int(canvas.get("width", 750)), int(canvas.get("height", 1050))
        colors = template.get("colors", {}) if isinstance(template.get("colors"), dict) else {}
        background = rgb(colors.get("background"), (40, 33, 52))
        border = rgb(colors.get("border"), (210, 185, 110))
        secondary = rgb(colors.get("secondary"), (120, 83, 185))
        text_color = rgb(colors.get("text"), (230, 215, 160))
        img = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(img)
        outer = box_for_layer(template, "outer_frame", (40, 40, width - 40, height - 40))
        inner = box_for_layer(template, "inner_frame", (74, 74, width - 74, height - 74))
        emblem = box_for_layer(template, "emblem", (190, 310, 560, 680))
        title = box_for_layer(template, "title", (80, 700, width - 80, 800))
        subtitle = box_for_layer(template, "subtitle", (80, 800, width - 80, 850))
        draw.rounded_rectangle(outer.as_tuple(), radius=int(layer_by_id(template, "outer_frame").get("radius", 42)), outline=border, width=8)
        draw.rounded_rectangle(inner.as_tuple(), radius=int(layer_by_id(template, "inner_frame").get("radius", 30)), outline=secondary, width=3)
        draw.ellipse(emblem.as_tuple(), outline=border, width=10)
        self._center_text(draw, "CARDFORGE", title.as_tuple(), self._font_role(template, "title"), fill=text_color)
        self._center_text(draw, project_name or "prototype card back", subtitle.as_tuple(), self._font_role(template, "subtitle"), fill=text_color)
        img.save(path)
        return {"rendered": True}

    def _draw_preview(self, front_path: Path, back_path: Path, preview_path: Path) -> None:
        front = Image.open(front_path).convert("RGB")
        back = Image.open(back_path).convert("RGB")
        preview_height = 700
        front.thumbnail((500, preview_height))
        back.thumbnail((500, preview_height))
        gutter = 24
        canvas = Image.new("RGB", (front.width + back.width + gutter, max(front.height, back.height)), (250, 247, 238))
        canvas.paste(front, (0, 0))
        canvas.paste(back, (front.width + gutter, 0))
        canvas.save(preview_path)

    def _cover_resize(self, image: Image.Image, width: int, height: int) -> Image.Image:
        src_ratio = image.width / image.height
        dst_ratio = width / height
        if src_ratio > dst_ratio:
            new_height = height
            new_width = int(height * src_ratio)
        else:
            new_width = width
            new_height = int(width / src_ratio)
        resized = image.resize((new_width, new_height))
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    def _center_text(self, draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], font: ImageFont.ImageFont, *, fill: tuple[int, int, int]) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        x = box[0] + ((box[2] - box[0]) - (bbox[2] - bbox[0])) // 2
        y = box[1] + ((box[3] - box[1]) - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text, font=font, fill=fill)

    def _font(self, size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def _font_role(self, template: dict[str, Any], role: str) -> ImageFont.ImageFont:
        roles = template.get("font_roles", {}) if isinstance(template.get("font_roles"), dict) else {}
        spec = roles.get(role, {}) if isinstance(roles.get(role), dict) else {}
        return self._font(int(spec.get("size", 24)))

    def _font_min(self, template: dict[str, Any], role: str, fallback: int) -> int:
        roles = template.get("font_roles", {}) if isinstance(template.get("font_roles"), dict) else {}
        spec = roles.get(role, {}) if isinstance(roles.get(role), dict) else {}
        return int(spec.get("min_size", fallback))

    def _colors(self, template: dict[str, Any]) -> dict[str, tuple[int, int, int]]:
        colors = template.get("colors", {}) if isinstance(template.get("colors"), dict) else {}
        return {
            "background": rgb(colors.get("background"), (236, 232, 220)),
            "border": rgb(colors.get("border"), (32, 28, 35)),
            "frame": rgb(colors.get("frame"), (70, 60, 82)),
            "panel": rgb(colors.get("panel"), (245, 241, 229)),
            "text": rgb(colors.get("text"), (25, 20, 20)),
            "muted_text": rgb(colors.get("muted_text"), (55, 45, 55)),
            "art_placeholder": rgb(colors.get("art_placeholder"), (135, 125, 145)),
        }

    def _front_layer_presence(self, template: dict[str, Any]) -> dict[str, bool]:
        required = ["title", "cost", "art", "type_line", "rules_text", "flavor_text", "stats"]
        return {layer_id: bool(layer_by_id(template, layer_id)) for layer_id in required}

    def _locked_art_candidate_id(self, conn, card_id: int) -> int | None:
        row = conn.execute(
            "SELECT id FROM art_candidates WHERE card_id = ? AND status = 'locked' ORDER BY updated_at DESC, id DESC LIMIT 1",
            (card_id,),
        ).fetchone()
        return int(row["id"]) if row else None
