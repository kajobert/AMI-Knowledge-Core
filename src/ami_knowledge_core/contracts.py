"""Core enums and immutable contracts shared by ingestion and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ImplementationStatus(StrEnum):
    DESIGN = "DESIGN"
    RESEARCH = "RESEARCH"
    EXPERIMENT = "EXPERIMENT"
    POC = "PoC"
    IMPLEMENTED = "IMPLEMENTED"
    VALIDATED = "VALIDATED"
    UNKNOWN = "UNKNOWN"


class LifecycleStatus(StrEnum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    DEAD_END = "DEAD_END"
    HISTORICAL = "HISTORICAL"
    UNRESOLVED = "UNRESOLVED"


class AccessClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Exact evidence anchor used by a derived claim."""

    source_id: str
    revision_id: str
    artifact_id: str
    chunk_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_id", self.source_id),
            ("revision_id", self.revision_id),
            ("artifact_id", self.artifact_id),
            ("chunk_id", self.chunk_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
