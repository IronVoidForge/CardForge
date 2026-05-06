from __future__ import annotations

from PIL import ImageDraw, ImageFont


class TextLayoutEngine:
    def wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
        lines: list[str] = []
        for paragraph in str(text or "").splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if self._width(candidate, font, draw) <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines

    def fit_font_size(self, text: str, font_path: str | None, *, max_width: int, max_height: int, start_size: int, min_size: int, draw: ImageDraw.ImageDraw) -> tuple[ImageFont.ImageFont, list[str], bool]:
        for size in range(start_size, min_size - 1, -1):
            font = self._font(font_path, size)
            lines = self.wrap_text(text, font, max_width, draw)
            line_height = self._line_height(font, draw)
            if len(lines) * line_height <= max_height:
                return font, lines, True
        font = self._font(font_path, min_size)
        return font, self.wrap_text(text, font, max_width, draw), False

    def _font(self, font_path: str | None, size: int) -> ImageFont.ImageFont:
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                pass
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def _width(self, text: str, font: ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    def _line_height(self, font: ImageFont.ImageFont, draw: ImageDraw.ImageDraw) -> int:
        box = draw.textbbox((0, 0), "Ag", font=font)
        return max(1, box[3] - box[1] + 8)
