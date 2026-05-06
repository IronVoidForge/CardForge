from __future__ import annotations

import json
import re
from typing import Any

from cardforge.services.llm.packet_core import parse_packet_document, sanitize_llm_text, strip_markdown_fences
from cardforge.services.llm.packet_sections import SECTION_TEXT_KEYS, canonical_section_name, normalize_key, plain_section_name
from cardforge.services.llm.packet_types import PacketParseError, PacketRecord


def parse_card_records(response: str, *, expected_task: str | None = "card_batch") -> list[PacketRecord]:
    """Parse card records from packet, JSON, markdown tables, or heading blocks."""
    cleaned = sanitize_llm_text(response)
    try:
        packet = parse_packet_document(cleaned, expected_task=expected_task)
        records = [record for record in packet.records if record.fields.get("type", "card").strip().lower() in {"", "card"}]
        if records:
            return records
    except PacketParseError:
        pass

    payload = extract_json_payload(cleaned)
    if payload is not None:
        records = records_from_json_payload(payload)
        if records:
            return records

    records = records_from_markdown_tables(cleaned)
    if records:
        return records

    records = records_from_heading_blocks(cleaned)
    if records:
        return records

    raise PacketParseError("No card records could be parsed from packet, JSON, markdown table, or heading blocks.")


def parse_card_records_flexible(response: str) -> list[PacketRecord]:
    return parse_card_records(response, expected_task="card_batch")


def extract_json_payload(text: str) -> Any | None:
    cleaned = strip_markdown_fences(text)
    for candidate in (cleaned, _slice_between(cleaned, "{", "}"), _slice_between(cleaned, "[", "]")):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def records_from_json_payload(payload: Any) -> list[PacketRecord]:
    if isinstance(payload, dict):
        raw_cards = payload.get("cards") or payload.get("records") or payload.get("card_batch") or []
    elif isinstance(payload, list):
        raw_cards = payload
    else:
        raw_cards = []
    records: list[PacketRecord] = []
    for item in raw_cards if isinstance(raw_cards, list) else []:
        if not isinstance(item, dict):
            continue
        fields: dict[str, str] = {"type": "card"}
        sections: dict[str, str] = {}
        for key, value in item.items():
            normalized = normalize_key(key)
            canonical = canonical_section_name(normalized)
            if canonical in SECTION_TEXT_KEYS:
                sections[canonical] = _stringify(value)
            else:
                fields[normalized] = _stringify(value)
        records.append(PacketRecord(fields=fields, sections=sections))
    return records


def records_from_markdown_tables(markdown: str) -> list[PacketRecord]:
    table_row_pattern = re.compile(r"^\|(.+)\|$")
    separator_pattern = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
    lines = markdown.splitlines()
    records: list[PacketRecord] = []
    index = 0
    while index < len(lines):
        header = lines[index].strip()
        if not table_row_pattern.fullmatch(header):
            index += 1
            continue
        if index + 1 >= len(lines) or not separator_pattern.fullmatch(lines[index + 1].strip()):
            index += 1
            continue
        headers = [normalize_key(cell) for cell in _split_markdown_table_row(header)]
        row_index = index + 2
        while row_index < len(lines):
            row = lines[row_index].strip()
            if not table_row_pattern.fullmatch(row):
                break
            cells = _split_markdown_table_row(row)
            if len(cells) == len(headers):
                data = {header: cell.strip() for header, cell in zip(headers, cells)}
                fields: dict[str, str] = {"type": "card"}
                sections: dict[str, str] = {}
                for key, value in data.items():
                    canonical = canonical_section_name(key)
                    if canonical in SECTION_TEXT_KEYS:
                        sections[canonical] = _clean_markdown_cell(value)
                    elif key == "type":
                        fields["card_type"] = _clean_markdown_cell(value)
                    else:
                        fields[key] = _clean_markdown_cell(value)
                if fields.get("name"):
                    records.append(PacketRecord(fields=fields, sections=sections))
            row_index += 1
        index = row_index
    return records


def records_from_heading_blocks(markdown: str) -> list[PacketRecord]:
    heading_pattern = re.compile(r"(?m)^#{1,3}\s+([^\r\n]+)\s*$")
    matches = list(heading_pattern.finditer(markdown))
    records: list[PacketRecord] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        if title.lower() in {"cards", "card list", "generated cards", "card batch"}:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        fields, sections = _parse_heading_card_block(title, markdown[start:end].strip())
        if fields.get("name") and (fields.get("card_type") or sections.get("rules_text")):
            fields.setdefault("card_type", "creature")
            records.append(PacketRecord(fields=fields, sections=sections))
    return records


def _parse_heading_card_block(title: str, block: str) -> tuple[dict[str, str], dict[str, str]]:
    fields: dict[str, str] = {"type": "card", "name": title.strip()}
    sections: dict[str, str] = {}
    current_section: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_section, current_lines
        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()
        current_section = None
        current_lines = []

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current_section:
                current_lines.append("")
            continue
        markdown_heading = re.fullmatch(r"#{2,5}\s+(.+)", stripped)
        maybe_section = plain_section_name(markdown_heading.group(1) if markdown_heading else stripped)
        if maybe_section:
            flush()
            current_section = maybe_section
            continue
        bullet = stripped[2:].strip() if stripped.startswith(("- ", "* ")) else stripped
        if current_section:
            current_lines.append(line)
            continue
        if ":" in bullet:
            key, value = bullet.split(":", 1)
            normalized = normalize_key(key)
            if normalized == "type":
                normalized = "card_type"
            fields[normalized] = value.strip()
    flush()
    for key in list(fields):
        canonical = canonical_section_name(key)
        if canonical in SECTION_TEXT_KEYS:
            sections[canonical] = fields.pop(key)
    return fields, sections


def _split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _clean_markdown_cell(value: str) -> str:
    return re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.IGNORECASE).strip()


def _slice_between(text: str, opener: str, closer: str) -> str:
    start = text.find(opener)
    end = text.rfind(closer)
    return text[start : end + 1] if start >= 0 and end > start else ""


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()
