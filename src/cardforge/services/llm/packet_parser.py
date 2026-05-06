from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


class PacketParseError(ValueError):
    """Raised when a model response cannot be read as a tagged packet or salvageable card output."""


@dataclass(frozen=True)
class PacketRecord:
    fields: dict[str, str]
    sections: dict[str, str]


@dataclass(frozen=True)
class PacketDocument:
    metadata: dict[str, str]
    sections: dict[str, str]
    records: list[PacketRecord]


SECTION_TAG_PATTERN = re.compile(r"^\[\[SECTION\s+([a-z0-9_\- ]+)\]\]$", re.IGNORECASE)
PACKET_VERSION = "1"


def parse_packet_document(response: str, *, expected_task: str | None = None) -> PacketDocument:
    packet_body = extract_packet_body(strip_markdown_fences(response))
    packet = parse_packet_body(packet_body)
    if expected_task is not None:
        actual_task = packet.metadata.get("task", "").strip()
        if actual_task and actual_task != expected_task:
            raise PacketParseError(f"Packet task '{actual_task}' did not match expected task '{expected_task}'.")
        if not actual_task:
            packet.metadata["task"] = expected_task
    version = packet.metadata.get("version", "").strip()
    if version and version != PACKET_VERSION:
        raise PacketParseError(f"Packet version '{version}' did not match expected version '{PACKET_VERSION}'.")
    if not version:
        packet.metadata["version"] = PACKET_VERSION
    return packet


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


def sanitize_llm_text(text: str) -> str:
    cleaned: list[str] = []
    for ch in str(text or ""):
        if ch in "\n\r\t":
            cleaned.append(ch)
            continue
        if unicodedata.category(ch) == "Cf":
            continue
        cleaned.append(ch)
    return "".join(cleaned).strip()


def strip_markdown_fences(response: str) -> str:
    cleaned = sanitize_llm_text(response)
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_packet_body(response: str) -> str:
    cleaned = sanitize_llm_text(response)
    lines = cleaned.splitlines()
    start_index = next((idx for idx, line in enumerate(lines) if normalize_structural_tag(line.strip()) == "PACKET_START"), -1)
    end_index = next((idx for idx in range(len(lines) - 1, -1, -1) if normalize_structural_tag(lines[idx].strip()) == "PACKET_END"), -1)
    if start_index >= 0 and end_index > start_index:
        return "\n".join(lines[start_index + 1 : end_index]).strip()
    if start_index >= 0:
        return "\n".join(lines[start_index + 1 :]).strip()
    raise PacketParseError("Response did not contain a CardForge packet envelope.")


def parse_packet_body(packet_body: str) -> PacketDocument:
    metadata: dict[str, str] = {}
    sections: dict[str, str] = {}
    records: list[PacketRecord] = []
    lines = packet_body.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        kind = normalize_structural_tag(stripped)
        if not stripped or kind in {"PACKET_END", "RECORD_END", "SECTION_END"}:
            index += 1
            continue
        if kind == "RECORD_START":
            body, index = collect_block(lines, index, start_kind="RECORD_START", end_kind="RECORD_END", fallback_stop_same_start=True)
            records.append(parse_packet_record(body))
            continue
        section_match = SECTION_TAG_PATTERN.fullmatch(stripped)
        if section_match:
            section_name = normalize_key(section_match.group(1))
            body, index = collect_block(lines, index, start_kind="SECTION_START", end_kind="SECTION_END", fallback_stop_any_tag=True)
            sections[section_name] = "\n".join(body).strip()
            continue
        key, value = split_key_value(stripped)
        if key.endswith("_markdown") and not value:
            body, index = collect_implicit_markdown_block(lines, index + 1)
            text = "\n".join(body).strip()
            metadata[key] = text
            sections.setdefault(key, text)
            continue
        metadata[key] = value
        index += 1
    return PacketDocument(metadata=metadata, sections=sections, records=records)


def parse_packet_record(record_lines: list[str]) -> PacketRecord:
    fields: dict[str, str] = {}
    sections: dict[str, str] = {}
    index = 0
    while index < len(record_lines):
        stripped = record_lines[index].strip()
        kind = normalize_structural_tag(stripped)
        if not stripped or kind in {"PACKET_END", "RECORD_END", "SECTION_END"}:
            index += 1
            continue
        section_match = SECTION_TAG_PATTERN.fullmatch(stripped)
        if section_match:
            section_name = normalize_key(section_match.group(1))
            body, index = collect_block(record_lines, index, start_kind="SECTION_START", end_kind="SECTION_END", fallback_stop_any_tag=True)
            sections[_canonical_section_name(section_name)] = "\n".join(body).strip()
            continue
        key, value = split_key_value(stripped)
        if key.endswith("_markdown") and not value:
            body, index = collect_implicit_markdown_block(record_lines, index + 1)
            sections[key] = "\n".join(body).strip()
            continue
        fields[key] = value
        index += 1
    fields.setdefault("type", infer_record_type(fields, sections))
    if not fields.get("type"):
        raise PacketParseError("Packet record is missing a type field.")
    return PacketRecord(fields=fields, sections=sections)


def collect_block(
    lines: list[str],
    start_index: int,
    *,
    start_kind: str,
    end_kind: str,
    fallback_stop_any_tag: bool = False,
    fallback_stop_same_start: bool = False,
) -> tuple[list[str], int]:
    if normalize_structural_tag(lines[start_index].strip()) != start_kind:
        raise PacketParseError(f"Expected {start_kind} at line {start_index + 1}.")
    body: list[str] = []
    index = start_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        kind = normalize_structural_tag(stripped)
        if kind == end_kind:
            return body, index + 1
        if fallback_stop_same_start and kind == start_kind:
            return body, index
        if fallback_stop_any_tag and kind in {"PACKET_START", "PACKET_END", "RECORD_START", "RECORD_END", "SECTION_START"}:
            return body, index
        body.append(lines[index])
        index += 1
    return body, index


def collect_implicit_markdown_block(lines: list[str], start_index: int) -> tuple[list[str], int]:
    body: list[str] = []
    index = start_index
    while index < len(lines):
        stripped = lines[index].strip()
        kind = normalize_structural_tag(stripped)
        if kind in {"PACKET_START", "PACKET_END", "RECORD_START", "RECORD_END", "SECTION_START", "SECTION_END"}:
            break
        if re.fullmatch(r"[a-z0-9_\- ]+:\s*$", stripped, flags=re.IGNORECASE):
            break
        body.append(lines[index])
        index += 1
    return body, index


def normalize_structural_tag(stripped: str) -> str | None:
    if SECTION_TAG_PATTERN.fullmatch(stripped):
        return "SECTION_START"
    if not stripped.startswith("[[") or not stripped.endswith("]]"):
        return None
    core = stripped[2:-2].strip().lower()
    normalized = re.sub(r"[^a-z0-9_/]+", "", core)
    if not normalized:
        return None
    is_end = normalized.startswith("/") or normalized.startswith("end") or "end" in normalized
    if "section" in normalized:
        return "SECTION_END" if is_end or normalized.startswith("/") else "SECTION_START"
    if "record" in normalized:
        return "RECORD_END" if is_end or normalized.startswith("/") else "RECORD_START"
    if "packet" in normalized:
        return "PACKET_END" if is_end or normalized.startswith("/") else "PACKET_START"
    return None


def split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise PacketParseError(f"Expected 'key: value' line but got: {line}")
    key, value = line.split(":", 1)
    key = normalize_key(key)
    if not key:
        raise PacketParseError(f"Empty packet key in line: {line}")
    return key, value.strip()


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def infer_record_type(fields: dict[str, str], sections: dict[str, str]) -> str:
    if any(key in fields for key in {"card_id", "card_key", "name", "card_type"}):
        return "card"
    if "rules_text" in sections or "art_direction" in sections:
        return "card"
    return ""


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
            canonical = _canonical_section_name(normalized)
            if canonical in {"rules_text", "flavor_text", "design_notes", "art_direction"}:
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
                    canonical = _canonical_section_name(key)
                    if canonical in {"rules_text", "flavor_text", "design_notes", "art_direction"}:
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
        maybe_section = _plain_section_name(markdown_heading.group(1) if markdown_heading else stripped)
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
        canonical = _canonical_section_name(key)
        if canonical in {"rules_text", "flavor_text", "design_notes", "art_direction"}:
            sections[canonical] = fields.pop(key)
    return fields, sections


def _canonical_section_name(value: str) -> str:
    return {
        "rules": "rules_text",
        "rule_text": "rules_text",
        "rules_text": "rules_text",
        "effect": "rules_text",
        "flavor": "flavor_text",
        "flavor_text": "flavor_text",
        "notes": "design_notes",
        "design_note": "design_notes",
        "design_notes": "design_notes",
        "art": "art_direction",
        "illustration": "art_direction",
        "art_direction": "art_direction",
    }.get(value, value)


def _plain_section_name(value: str) -> str | None:
    canonical = _canonical_section_name(normalize_key(value))
    if canonical in {"rules_text", "flavor_text", "design_notes", "art_direction"}:
        return canonical
    return None


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
