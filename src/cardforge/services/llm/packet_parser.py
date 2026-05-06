from __future__ import annotations

from cardforge.services.llm.card_record_salvage import (
    extract_json_payload,
    parse_card_records,
    parse_card_records_flexible,
    records_from_heading_blocks,
    records_from_json_payload,
    records_from_markdown_tables,
)
from cardforge.services.llm.packet_core import (
    collect_block,
    collect_implicit_markdown_block,
    extract_packet_body,
    infer_record_type,
    normalize_structural_tag,
    parse_packet_body,
    parse_packet_document,
    parse_packet_record,
    sanitize_llm_text,
    split_key_value,
    strip_markdown_fences,
)
from cardforge.services.llm.packet_sections import canonical_section_name, normalize_key, plain_section_name
from cardforge.services.llm.packet_types import PacketDocument, PacketParseError, PacketRecord

__all__ = [
    "PacketDocument",
    "PacketParseError",
    "PacketRecord",
    "canonical_section_name",
    "collect_block",
    "collect_implicit_markdown_block",
    "extract_json_payload",
    "extract_packet_body",
    "infer_record_type",
    "normalize_key",
    "normalize_structural_tag",
    "parse_card_records",
    "parse_card_records_flexible",
    "parse_packet_body",
    "parse_packet_document",
    "parse_packet_record",
    "plain_section_name",
    "records_from_heading_blocks",
    "records_from_json_payload",
    "records_from_markdown_tables",
    "sanitize_llm_text",
    "split_key_value",
    "strip_markdown_fences",
]
