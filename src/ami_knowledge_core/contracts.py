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


class SensitivityClass(StrEnum):
    PUBLIC_OR_LOW_SENSITIVITY = "PUBLIC_OR_LOW_SENSITIVITY"
    PRIVATE_PROJECT = "PRIVATE_PROJECT"
    PERSONAL_PRIVATE = "PERSONAL_PRIVATE"
    SECRET_LIKE = "SECRET_LIKE"
    CREDENTIAL_CONFIRMED = "CREDENTIAL_CONFIRMED"
    UNSAFE_TO_EXTERNALIZE = "UNSAFE_TO_EXTERNALIZE"


class EvidenceKind(StrEnum):
    DIRECT_QUOTE = "DIRECT_QUOTE"
    SOURCE_PARAPHRASE = "SOURCE_PARAPHRASE"
    DERIVED_RELATIONSHIP = "DERIVED_RELATIONSHIP"
    MODEL_HYPOTHESIS = "MODEL_HYPOTHESIS"
    QUESTION_CANDIDATE = "QUESTION_CANDIDATE"


class CanonicalStatus(StrEnum):
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    CURRENT_CANDIDATE = "CURRENT_CANDIDATE"
    CANONICAL = "CANONICAL"
    REJECTED = "REJECTED"


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
