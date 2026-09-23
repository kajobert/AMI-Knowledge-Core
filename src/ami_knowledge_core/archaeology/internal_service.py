"""Bounded internal mutation service for Control Plane-owned archaeology.

This module is deliberately not an HTTP/MCP surface. It exposes typed host-side
operations that preserve work/campaign provenance and deterministic validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import connect
from .campaign import CampaignBinding, register_campaign, register_corpus_snapshot
from .evidence import CandidateEvidence, insert_validated_candidate


@dataclass(frozen=True, slots=True)
class EvidenceSubmissionResult:
    evidence_id: str
    accepted: bool = True


class ArchaeologyInternalService:
    def register_snapshot(
        self,
        *,
        revision_refs: tuple[str, ...],
        source_registry_version: str,
        parser_policy_version: str,
        sensitivity_policy_version: str,
    ) -> str:
        return register_corpus_snapshot(
            revision_refs=revision_refs,
            source_registry_version=source_registry_version,
            parser_policy_version=parser_policy_version,
            sensitivity_policy_version=sensitivity_policy_version,
        )

    def register_campaign(
        self,
        *,
        work_ref: str,
        corpus_snapshot_id: str,
        campaign_version: str,
        policy_bundle_hash: str,
        slot_limit: int = 15,
    ) -> CampaignBinding:
        return register_campaign(
            work_ref=work_ref,
            corpus_snapshot_id=corpus_snapshot_id,
            campaign_version=campaign_version,
            policy_bundle_hash=policy_bundle_hash,
            slot_limit=slot_limit,
        )

    def submit_candidate_evidence(
        self,
        packet: CandidateEvidence,
        *,
        idempotency_key: str,
    ) -> EvidenceSubmissionResult:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key_required")
        with connect() as connection, connection.cursor() as cursor:
            evidence_id = insert_validated_candidate(
                cursor,
                packet,
                idempotency_key=idempotency_key,
            )
            connection.commit()
        return EvidenceSubmissionResult(evidence_id=evidence_id)
