"""Provenance-safe claim and canonical promotion rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import psycopg

from .contracts import EvidenceRef
from .db import connect
from .identity import stable_id


class ProvenanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimDraft:
    subject: str
    predicate: str
    object_value: str
    claim_text: str
    entity_id: str | None
    evidence: tuple[EvidenceRef, ...]
    validation_status: Literal["PROPOSED", "SUPPORTED", "VALIDATED", "REJECTED"] = "PROPOSED"


def _evidence_exists(cursor: psycopg.Cursor[Any], ref: EvidenceRef) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM kc_chunk c
        JOIN kc_artifact a ON a.artifact_id = c.artifact_id
        JOIN kc_source_revision r ON r.revision_id = c.revision_id
        JOIN kc_source s ON s.source_id = r.source_id
        WHERE c.chunk_id = %s
          AND a.artifact_id = %s
          AND r.revision_id = %s
          AND s.source_id = %s
        """,
        (ref.chunk_id, ref.artifact_id, ref.revision_id, ref.source_id),
    )
    return cursor.fetchone() is not None


def validate_claim_draft(draft: ClaimDraft) -> None:
    if draft.validation_status == "VALIDATED" and not draft.evidence:
        raise ProvenanceError("validated claim requires supporting evidence")

    with connect() as connection, connection.cursor() as cursor:
        for ref in draft.evidence:
            if not _evidence_exists(cursor, ref):
                raise ProvenanceError(f"unknown provenance chunk_id: {ref.chunk_id}")


def insert_claim(draft: ClaimDraft, *, claim_id: str | None = None) -> str:
    validate_claim_draft(draft)
    resolved_id = claim_id or stable_id(
        "claim",
        draft.subject,
        draft.predicate,
        draft.object_value,
        draft.claim_text,
    )
    status = draft.validation_status
    if status == "VALIDATED" and not draft.evidence:
        raise ProvenanceError("validated claim requires supporting evidence")
    if status == "VALIDATED":
        status = "SUPPORTED"

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO kc_claim (
                  claim_id, entity_id, subject, predicate, object_value,
                  claim_text, validation_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (claim_id) DO NOTHING
                """,
                (
                    resolved_id,
                    draft.entity_id,
                    draft.subject,
                    draft.predicate,
                    draft.object_value,
                    draft.claim_text,
                    status,
                ),
            )
            for ref in draft.evidence:
                cursor.execute(
                    """
                    INSERT INTO kc_claim_evidence (
                      claim_id, chunk_id, source_id, revision_id, artifact_id, relation
                    ) VALUES (%s, %s, %s, %s, %s, 'supports')
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        resolved_id,
                        ref.chunk_id,
                        ref.source_id,
                        ref.revision_id,
                        ref.artifact_id,
                    ),
                )
        connection.commit()
    return resolved_id


def promote_canonical_record(
    *,
    canonical_id: str,
    record_type: str,
    title: str,
    body: dict[str, Any],
    supporting_claim_ids: list[str],
    opposing_claim_ids: list[str],
    promoted_by: str,
) -> None:
    if promoted_by.lower() == "llm":
        raise ProvenanceError("LLM actors cannot promote canonical records")

    with connect() as connection:
        with connection.cursor() as cursor:
            all_ids = supporting_claim_ids + opposing_claim_ids
            for claim_id in all_ids:
                cursor.execute("SELECT claim_id FROM kc_claim WHERE claim_id = %s", (claim_id,))
                if cursor.fetchone() is None:
                    raise ProvenanceError(f"unknown claim_id for canonical promotion: {claim_id}")

            cursor.execute(
                """
                INSERT INTO kc_canonical_record (
                  canonical_id, record_type, title, body,
                  supporting_claim_ids, opposing_claim_ids, promoted_by
                ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    canonical_id,
                    record_type,
                    title,
                    json.dumps(body),
                    json.dumps(supporting_claim_ids),
                    json.dumps(opposing_claim_ids),
                    promoted_by,
                ),
            )
        connection.commit()

