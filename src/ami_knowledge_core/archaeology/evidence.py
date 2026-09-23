"""Candidate-evidence contract and deterministic Phase 1 validator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import psycopg

from ..contracts import CanonicalStatus, EvidenceKind, LifecycleStatus, SensitivityClass
from ..identity import canonical_json, stable_id
from .campaign import require_campaign_binding
from .security import contains_secret_like_material


EVIDENCE_SCHEMA_VERSION = "archaeology-evidence-v1"
VALID_SPAN_TYPES = {"text", "conversation", "pdf", "image", "git"}


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    work_ref: str
    campaign_id: str
    task_id: str
    run_id: str
    source_id: str
    revision_id: str
    source_hash: str
    source_span: dict[str, Any]
    source_chunk_id: str | None
    claim_text: str
    claim_type: str
    domain_tags: tuple[str, ...]
    evidence_kind: EvidenceKind
    extractor_role: str
    backend: str
    sensitivity_class: SensitivityClass
    historical_status: LifecycleStatus = LifecycleStatus.UNRESOLVED
    canonical_status: CanonicalStatus = CanonicalStatus.EVIDENCE_ONLY
    model: str | None = None
    prompt_template_version: str | None = None
    model_confidence: float | None = None
    source_time_context: dict[str, Any] | None = None
    entity_refs: tuple[str, ...] = ()
    project_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceValidation:
    ok: bool
    checks: tuple[dict[str, str], ...]
    safe_error_codes: tuple[str, ...]


def semantic_hash(packet: CandidateEvidence) -> str:
    material = {
        "claim_text": packet.claim_text.strip(),
        "claim_type": packet.claim_type.strip(),
        "evidence_kind": packet.evidence_kind.value,
        "source_id": packet.source_id,
        "revision_id": packet.revision_id,
        "source_span": packet.source_span,
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def packet_hash(packet: CandidateEvidence) -> str:
    payload = asdict(packet)
    payload["evidence_kind"] = packet.evidence_kind.value
    payload["sensitivity_class"] = packet.sensitivity_class.value
    payload["historical_status"] = packet.historical_status.value
    payload["canonical_status"] = packet.canonical_status.value
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def validate_source_span(span: dict[str, Any]) -> bool:
    span_type = str(span.get("type", ""))
    if span_type not in VALID_SPAN_TYPES:
        return False
    if span_type == "text":
        start = span.get("start_byte")
        end = span.get("end_byte")
        return isinstance(start, int) and isinstance(end, int) and 0 <= start < end
    if span_type == "conversation":
        return bool(span.get("message_id"))
    if span_type == "pdf":
        return isinstance(span.get("page"), int) and span["page"] >= 1
    if span_type == "image":
        return bool(span.get("image_id"))
    if span_type == "git":
        return bool(span.get("commit_sha") and span.get("path"))
    return False


def validate_candidate_evidence(
    cursor: psycopg.Cursor[Any],
    packet: CandidateEvidence,
) -> EvidenceValidation:
    checks: list[dict[str, str]] = []
    errors: list[str] = []

    def record(name: str, passed: bool, code: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL"})
        if not passed:
            errors.append(code)

    binding = None
    try:
        binding = require_campaign_binding(
            cursor,
            campaign_id=packet.campaign_id,
            work_ref=packet.work_ref,
        )
        record("campaign_work_binding", True, "campaign_work_ref_mismatch")
    except ValueError:
        record("campaign_work_binding", False, "campaign_work_ref_mismatch")

    if binding is not None:
        cursor.execute(
            """
            SELECT revision_refs
            FROM kc_corpus_snapshot
            WHERE corpus_snapshot_id = %s
            """,
            (binding.corpus_snapshot_id,),
        )
        snapshot = cursor.fetchone()
        revision_refs: list[str] = []
        if snapshot is not None:
            raw_refs = snapshot["revision_refs"]
            revision_refs = json.loads(raw_refs) if isinstance(raw_refs, str) else list(raw_refs)
        record(
            "revision_in_campaign_snapshot",
            packet.revision_id in revision_refs,
            "campaign_snapshot_mismatch",
        )

    cursor.execute(
        """
        SELECT r.content_sha256, r.source_id
        FROM kc_source_revision r
        WHERE r.revision_id = %s
        """,
        (packet.revision_id,),
    )
    revision = cursor.fetchone()
    record("revision_exists", revision is not None, "evidence_provenance_invalid")
    if revision is not None:
        record(
            "revision_source_binding",
            str(revision["source_id"]) == packet.source_id,
            "evidence_provenance_invalid",
        )
        record(
            "source_hash_matches",
            str(revision["content_sha256"]) == packet.source_hash,
            "source_hash_mismatch",
        )

    if packet.source_chunk_id is not None:
        cursor.execute(
            """
            SELECT 1
            FROM kc_chunk c
            JOIN kc_artifact a ON a.artifact_id = c.artifact_id
            WHERE c.chunk_id = %s
              AND c.revision_id = %s
              AND a.source_id = %s
            """,
            (packet.source_chunk_id, packet.revision_id, packet.source_id),
        )
        record(
            "chunk_binding",
            cursor.fetchone() is not None,
            "evidence_provenance_invalid",
        )

    record(
        "source_span",
        validate_source_span(packet.source_span),
        "source_span_invalid",
    )
    record(
        "secret_scan",
        not contains_secret_like_material(packet.claim_text),
        "secret_like_output_rejected",
    )
    record(
        "model_hypothesis_not_direct_quote",
        not (
            packet.evidence_kind is EvidenceKind.MODEL_HYPOTHESIS
            and packet.claim_type.upper() in {"DIRECT_FACT", "DIRECT_QUOTE"}
        ),
        "evidence_kind_invalid",
    )
    record("claim_bounded", 0 < len(packet.claim_text.encode("utf-8")) <= 16_000, "evidence_too_large")

    return EvidenceValidation(
        ok=not errors,
        checks=tuple(checks),
        safe_error_codes=tuple(sorted(set(errors))),
    )


def insert_validated_candidate(
    cursor: psycopg.Cursor[Any],
    packet: CandidateEvidence,
    *,
    idempotency_key: str,
    validator_version: str = "phase1-validator-v1",
    policy_version: str = "phase1-security-v1",
) -> str:
    validation = validate_candidate_evidence(cursor, packet)
    if not validation.ok:
        raise ValueError(",".join(validation.safe_error_codes))

    sem_hash = semantic_hash(packet)
    pkt_hash = packet_hash(packet)
    evidence_id = stable_id(
        "candidate_evidence",
        packet.campaign_id,
        idempotency_key,
        pkt_hash,
    )
    cursor.execute(
        """
        SELECT evidence_id, packet_hash
        FROM kc_candidate_evidence
        WHERE campaign_id = %s AND idempotency_key = %s
        """,
        (packet.campaign_id, idempotency_key),
    )
    existing = cursor.fetchone()
    if existing is not None:
        if str(existing["packet_hash"]) != pkt_hash:
            raise ValueError("evidence_idempotency_conflict")
        return str(existing["evidence_id"])

    cursor.execute(
        """
        INSERT INTO kc_candidate_evidence (
          evidence_id, evidence_schema_version, work_ref, campaign_id, task_id, run_id,
          source_id, revision_id, source_hash, source_span, source_chunk_id,
          source_time_context, claim_text, claim_type, domain_tags, entity_refs, project_refs,
          evidence_kind, extractor_role, backend, model, prompt_template_version,
          model_confidence, historical_status, canonical_status, sensitivity_class,
          validation_status, semantic_hash, packet_hash, idempotency_key
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
          %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PASS', %s, %s, %s
        )
        """,
        (
            evidence_id,
            EVIDENCE_SCHEMA_VERSION,
            packet.work_ref,
            packet.campaign_id,
            packet.task_id,
            packet.run_id,
            packet.source_id,
            packet.revision_id,
            packet.source_hash,
            json.dumps(packet.source_span),
            packet.source_chunk_id,
            json.dumps(packet.source_time_context) if packet.source_time_context else None,
            packet.claim_text,
            packet.claim_type,
            json.dumps(list(packet.domain_tags)),
            json.dumps(list(packet.entity_refs)),
            json.dumps(list(packet.project_refs)),
            packet.evidence_kind.value,
            packet.extractor_role,
            packet.backend,
            packet.model,
            packet.prompt_template_version,
            packet.model_confidence,
            packet.historical_status.value,
            packet.canonical_status.value,
            packet.sensitivity_class.value,
            sem_hash,
            pkt_hash,
            idempotency_key,
        ),
    )
    validation_id = stable_id("evidence_validation", evidence_id, validator_version, policy_version)
    cursor.execute(
        """
        INSERT INTO kc_evidence_validation (
          validation_id, evidence_id, validator_version, policy_version,
          status, checks, safe_error_codes
        ) VALUES (%s, %s, %s, %s, 'PASS', %s::jsonb, %s::jsonb)
        ON CONFLICT (validation_id) DO NOTHING
        """,
        (
            validation_id,
            evidence_id,
            validator_version,
            policy_version,
            json.dumps(list(validation.checks)),
            json.dumps(list(validation.safe_error_codes)),
        ),
    )
    return evidence_id
