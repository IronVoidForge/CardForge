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
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.render.text_layout import TextLayoutEngine
from cardforge.services.review.review_service import ReviewService


class CardRenderer:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.text = TextLayoutEngine()

    def render_card(self, project_slug: str, card_key: str, *, placeholder_art: bool = True) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            render_key = next_key(conn, "renders", "render_key", "RENDER", where="card_id = ?", params=(card["id"],))
            render_root = self.asset_store.project_root(project_slug) / "cards" / card_key / "renders"
            render_root.mkdir(parents=True, exist_ok=True)
            front_path = render_root / f"front_{render_key.lower()}.png"
            back_path = render_root / f"back_{render_key.lower()}.png"
            preview_path = render_root / f"preview_{render_key.lower()}.png"
            layout_report = self._draw_front(card, front_path, placeholder_art=placeholder_art)
            self._draw_back(card, back_path)
            self._draw_preview(front_path, back_path, preview_path)
            status = RenderStatus.RENDERED.value if layout_report["all_text_fit"] else RenderStatus.LAYOUT_WARNING.value
            conn.execute(
                """
                INSERT INTO renders(card_id, card_version_id, render_key, front_path, back_path, preview_path, layout_report_json, status)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card["id"], card["current_version_id"], render_key,
                    self.asset_store.relative_to_workspace(front_path),
                    self.asset_store.relative_to_workspace(back_path),
                    self.asset_store.relative_to_workspace(preview_path),
                    json.dumps(layout_report), status,
                ),
            )
            conn.execute("UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (CardStatus.RENDERED.value, card["id"]))
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

    def _draw_front(self, card: Row, path: Path, *, placeholder_art: bool) -> dict[str, Any]:
        width, height = 750, 1050
        img = Image.new("RGB", (width, height), (236, 232, 220))
        draw = ImageDraw.Draw(img)
        border = (32, 28, 35)
        frame = (70, 60, 82)
        draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=34, fill=border)
        draw.rounded_rectangle((46, 46, width - 46, height - 46), radius=24, fill=(221, 213, 196))
        draw.rounded_rectangle((64, 64, width - 64, 150), radius=14, fill=(245, 241, 229), outline=frame, width=3)
        title_font = self._font(40)
        draw.text((86, 86), card["name"], fill=(25, 20, 20), font=title_font)
        cost = json.loads(card["cost_json"] or "{}")
        draw.ellipse((625, 78, 690, 143), fill=(245, 245, 235), outline=frame, width=3)
        draw.text((646, 94), str(cost.get("display", "")), fill=(20, 20, 20), font=self._font(30))
        art_box = (78, 170, 672, 520)
        draw.rectangle(art_box, fill=(135, 125, 145), outline=frame, width=4)
        if placeholder_art:
            self._center_text(draw, "PLACEHOLDER ART", art_box, self._font(34), fill=(240, 235, 220))
        draw.rounded_rectangle((78, 535, 672, 590), radius=8, fill=(245, 241, 229), outline=frame, width=3)
        draw.text((96, 548), card["type_line"], fill=(25, 20, 20), font=self._font(28))
        rules_box = (92, 620, 658, 865)
        draw.rounded_rectangle((78, 605, 672, 890), radius=10, fill=(248, 246, 238), outline=frame, width=3)
        rules_font, rules_lines, rules_fit = self.text.fit_font_size(card["rules_text"], None, max_width=rules_box[2]-rules_box[0], max_height=rules_box[3]-rules_box[1], start_size=27, min_size=17, draw=draw)
        y = rules_box[1]
        line_height = 32 if rules_fit else 25
        for line in rules_lines[:12]:
            draw.text((rules_box[0], y), line, fill=(20, 20, 20), font=rules_font)
            y += line_height
        flavor = card["flavor_text"] or ""
        if flavor:
            flavor_font, flavor_lines, flavor_fit = self.text.fit_font_size(flavor, None, max_width=540, max_height=75, start_size=21, min_size=15, draw=draw)
            y = 905
            for line in flavor_lines[:3]:
                draw.text((94, y), line, fill=(55, 45, 55), font=flavor_font)
                y += 24
        else:
            flavor_fit = True
        stats = json.loads(card["stats_json"] or "{}")
        if stats.get("attack") is not None or stats.get("health") is not None:
            draw.rounded_rectangle((560, 930, 680, 995), radius=16, fill=(245, 241, 229), outline=frame, width=4)
            draw.text((587, 944), f"{stats.get('attack', '-')}/{stats.get('health', '-')}", fill=(20, 20, 20), font=self._font(32))
        img.save(path)
        return {"rules_text_fit": rules_fit, "flavor_text_fit": flavor_fit, "all_text_fit": rules_fit and flavor_fit}

    def _draw_back(self, card: Row, path: Path) -> None:
        width, height = 750, 1050
        img = Image.new("RGB", (width, height), (40, 33, 52))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((40, 40, width - 40, height - 40), radius=42, outline=(210, 185, 110), width=8)
        draw.ellipse((190, 310, 560, 680), outline=(210, 185, 110), width=10)
        self._center_text(draw, "CARDFORGE", (80, 700, 670, 800), self._font(58), fill=(230, 215, 160))
        self._center_text(draw, "prototype card back", (80, 800, 670, 850), self._font(24), fill=(230, 215, 160))
        img.save(path)

    def _draw_preview(self, front_path: Path, back_path: Path, preview_path: Path) -> None:
        front = Image.open(front_path).resize((300, 420))
        back = Image.open(back_path).resize((300, 420))
        preview = Image.new("RGB", (640, 460), (230, 230, 230))
        preview.paste(front, (20, 20))
        preview.paste(back, (320, 20))
        preview.save(preview_path)

    def _font(self, size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def _center_text(self, draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], font: ImageFont.ImageFont, *, fill: tuple[int, int, int]) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        x = box[0] + ((box[2] - box[0]) - (bbox[2] - bbox[0])) // 2
        y = box[1] + ((box[3] - box[1]) - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text, font=font, fill=fill)
