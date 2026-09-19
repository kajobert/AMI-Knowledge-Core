"""Extraction adapter interface (no concrete LLM provider coupling)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .contract import EvidenceAnchor, ExtractedClaim, ExtractedEntity, ExtractionResult


class ExtractionAdapter(ABC):
    adapter_name: str

    @abstractmethod
    def extract(
        self,
        *,
        source_id: str,
        revision_id: str,
        chunk_evidence: tuple[EvidenceAnchor, ...],
        context: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        raise NotImplementedError


class HeuristicExtractionAdapter(ExtractionAdapter):
    """Deterministic dev/test extractor — not an LLM."""

    adapter_name = "heuristic-v0"

    def extract(
        self,
        *,
        source_id: str,
        revision_id: str,
        chunk_evidence: tuple[EvidenceAnchor, ...],
        context: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        if not chunk_evidence:
            return ExtractionResult(source_id=source_id, revision_id=revision_id)
        anchor = chunk_evidence[0]
        entity_key = f"entity:{source_id}"
        claim_key = f"claim:{revision_id}:summary"
        return ExtractionResult(
            source_id=source_id,
            revision_id=revision_id,
            entities=(
                ExtractedEntity(
                    key=entity_key,
                    entity_type="concept",
                    name=context.get("slug", source_id) if context else source_id,
                    summary="Heuristic archaeology extraction (dev adapter).",
                    lifecycle_proposal="UNRESOLVED",
                    confidence=0.55,
                ),
            ),
            claims=(
                ExtractedClaim(
                    key=claim_key,
                    subject=context.get("slug", "source") if context else "source",
                    predicate="has_archaeology_evidence",
                    object_value="chunk",
                    claim_text="Source revision contains indexed archaeology evidence chunks.",
                    evidence=(anchor,),
                    entity_key=entity_key,
                    lifecycle_proposal="UNRESOLVED",
                    confidence=0.55,
                ),
            ),
            open_questions=("Requires human review before canonical alignment.",),
            metadata={"adapter": self.adapter_name},
        )

