from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")


@dataclass(frozen=True)
class MarkdownDocument:
    sections: dict[str, str] = field(default_factory=dict)
    ordered_headings: list[str] = field(default_factory=list)
    preamble: str = ""

    def section(self, name: str, default: str = "") -> str:
        return self.sections.get(normalize_heading(name), default)


def normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def parse_markdown_sections(text: str) -> MarkdownDocument:
    """Flexible section parser for prompt packages and model-ish markdown.

    It accepts # through ###### headings, keeps duplicate headings by appending
    their bodies, preserves a preamble, and normalizes section keys to snake_case.
    """
    sections: dict[str, list[str]] = {}
    ordered: list[str] = []
    preamble: list[str] = []
    current: str | None = None
    for raw_line in str(text or "").replace("\r\n", "\n").splitlines():
        match = HEADING_RE.match(raw_line.strip())
        if match:
            current = normalize_heading(match.group(2))
            if current not in sections:
                sections[current] = []
                ordered.append(current)
            continue
        if current is None:
            preamble.append(raw_line)
        else:
            sections[current].append(raw_line)
    cleaned = {key: "\n".join(lines).strip() for key, lines in sections.items()}
    return MarkdownDocument(sections=cleaned, ordered_headings=ordered, preamble="\n".join(preamble).strip())


def parse_bullet_key_values(markdown: str) -> dict[str, str]:
    """Parse common prompt-package `- key: value` or `key: value` lines."""
    parsed: dict[str, str] = {}
    current_key: str | None = None
    continuation: list[str] = []

    def flush() -> None:
        nonlocal current_key, continuation
        if current_key:
            suffix = "\n".join(line.rstrip() for line in continuation).strip()
            if suffix:
                parsed[current_key] = (parsed.get(current_key, "") + "\n" + suffix).strip()
        current_key = None
        continuation = []

    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            if current_key:
                continuation.append("")
            continue
        if line.startswith(('-', '*')):
            line = line[1:].strip()
        if ":" in line and re.match(r"^[A-Za-z0-9_\- ]+\s*:", line):
            flush()
            key, value = line.split(":", 1)
            current_key = normalize_heading(key)
            parsed[current_key] = value.strip()
            continue
        if current_key:
            continuation.append(raw_line)
    flush()
    return parsed


def parse_markdown_tables(markdown: str) -> list[list[dict[str, str]]]:
    """Return every pipe table as a list of row dicts with normalized headers."""
    lines = str(markdown or "").splitlines()
    tables: list[list[dict[str, str]]] = []
    index = 0
    while index < len(lines):
        header_line = lines[index].strip()
        if not TABLE_ROW_RE.fullmatch(header_line) or index + 1 >= len(lines):
            index += 1
            continue
        sep_line = lines[index + 1].strip()
        if not TABLE_SEPARATOR_RE.fullmatch(sep_line):
            index += 1
            continue
        headers = [normalize_heading(cell) for cell in split_table_row(header_line)]
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and TABLE_ROW_RE.fullmatch(lines[index].strip()):
            cells = split_table_row(lines[index].strip())
            rows.append({header: clean_cell(cell) for header, cell in zip(headers, cells)})
            index += 1
        if rows:
            tables.append(rows)
    return tables


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def clean_cell(value: str) -> str:
    return str(value or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n").strip()


def compact_jsonish(value: Any) -> str:
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "").strip()
