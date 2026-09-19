"""Synthesis / alignment proposals (review-gated, no auto-canonical)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..extraction.contract import LifecycleProposal

AlignmentClass = LifecycleProposal


@dataclass(frozen=True, slots=True)
class SynthesisProposal:
    key: str
    source_id: str
    revision_id: str
    classification: AlignmentClass
    summary: str
    supporting_evidence: tuple[dict[str, str], ...] = ()
    opposing_evidence: tuple[dict[str, str], ...] = ()
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

