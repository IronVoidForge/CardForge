from __future__ import annotations

import re
import unicodedata

from cardforge.services.llm.packet_sections import canonical_section_name, normalize_key
from cardforge.services.llm.packet_types import PACKET_VERSION, PacketDocument, PacketParseError, PacketRecord

SECTION_TAG_PATTERN = re.compile(r"^\[\[SECTION\s+([a-z0-9_\- ]+)\]\]$", re.IGNORECASE)


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
            sections[canonical_section_name(section_name)] = "\n".join(body).strip()
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


def infer_record_type(fields: dict[str, str], sections: dict[str, str]) -> str:
    if any(key in fields for key in {"card_id", "card_key", "name", "card_type"}):
        return "card"
    if "rules_text" in sections or "art_direction" in sections:
        return "card"
    return ""
