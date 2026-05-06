from __future__ import annotations

from dataclasses import dataclass

PACKET_VERSION = "1"


class PacketParseError(ValueError):
    """Raised when a model response cannot be read as tagged or salvageable card output."""


@dataclass(frozen=True)
class PacketRecord:
    fields: dict[str, str]
    sections: dict[str, str]


@dataclass(frozen=True)
class PacketDocument:
    metadata: dict[str, str]
    sections: dict[str, str]
    records: list[PacketRecord]
