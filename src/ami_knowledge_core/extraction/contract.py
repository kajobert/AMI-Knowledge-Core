"""Provider-neutral structured extraction contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LifecycleProposal = Literal[
    "CURRENT",
    "HISTORICAL",
    "SUPERSEDED",
    "PARTIAL",
    "CONFLICT",
    "UNRESOLVED",
    "REUSABLE_IDEA",
    "NO_ACTION",
]


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    source_id: str
    revision_id: str
    artifact_id: str
    chunk_id: str


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    key: str
    entity_type: str
    name: str
    summary: str | None = None
    lifecycle_proposal: LifecycleProposal = "UNRESOLVED"
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    key: str
    subject: str
    predicate: str
    object_value: str
    claim_text: str
    evidence: tuple[EvidenceAnchor, ...]
    entity_key: str | None = None
    lifecycle_proposal: LifecycleProposal = "UNRESOLVED"
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExtractedRelationship:
    key: str
    from_entity_key: str
    to_entity_key: str
    relationship_type: str
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExtractedDecision:
    key: str
    title: str
    body: str
    evidence: tuple[EvidenceAnchor, ...]
    lifecycle_proposal: LifecycleProposal = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    revision_id: str
    source_id: str
    entities: tuple[ExtractedEntity, ...] = ()
    claims: tuple[ExtractedClaim, ...] = ()
    relationships: tuple[ExtractedRelationship, ...] = ()
    decisions: tuple[ExtractedDecision, ...] = ()
    implementation_references: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

