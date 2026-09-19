"""Apply validated extraction results idempotently (no canonical promotion)."""

from __future__ import annotations

import json
from typing import Any

import psycopg

from ..identity import stable_id
from .contract import ExtractionResult


def apply_extraction(
    cursor: psycopg.Cursor[Any],
    *,
    job_id: str,
    processing_fingerprint: str,
    result: ExtractionResult,
) -> dict[str, int]:
    counts = {"entities": 0, "claims": 0, "relationships": 0, "decisions": 0}
    entity_ids: dict[str, str] = {}

    for entity in result.entities:
        entity_id = stable_id("entity", processing_fingerprint, entity.key)
        record_key = entity.key
        cursor.execute(
            """
            INSERT INTO kc_derived_record (
              derived_id, job_id, derived_kind, record_key, processing_fingerprint, payload
            ) VALUES (%s, %s, 'entity', %s, %s, %s::jsonb)
            ON CONFLICT (derived_kind, record_key, processing_fingerprint) DO NOTHING
            """,
            (
                stable_id("derived", job_id, "entity", record_key),
                job_id,
                record_key,
                processing_fingerprint,
                json.dumps({"entity_id": entity_id}),
            ),
        )
        if cursor.rowcount:
            counts["entities"] += 1
        cursor.execute(
            """
            INSERT INTO kc_entity (
              entity_id, entity_type, name, summary, lifecycle_status, metadata
            ) VALUES (%s, %s, %s, %s, 'UNRESOLVED', %s::jsonb)
            ON CONFLICT (entity_id) DO NOTHING
            """,
            (
                entity_id,
                entity.entity_type,
                entity.name,
                entity.summary,
                json.dumps(
                    {
                        "lifecycle_proposal": entity.lifecycle_proposal,
                        "confidence": entity.confidence,
                        "processing_fingerprint": processing_fingerprint,
                    }
                ),
            ),
        )
        entity_ids[entity.key] = entity_id

    for claim in result.claims:
        claim_id = stable_id("claim", processing_fingerprint, claim.key)
        record_key = claim.key
        cursor.execute(
            """
            INSERT INTO kc_derived_record (
              derived_id, job_id, derived_kind, record_key, processing_fingerprint, payload
            ) VALUES (%s, %s, 'claim', %s, %s, %s::jsonb)
            ON CONFLICT (derived_kind, record_key, processing_fingerprint) DO NOTHING
            """,
            (
                stable_id("derived", job_id, "claim", record_key),
                job_id,
                record_key,
                processing_fingerprint,
                json.dumps({"claim_id": claim_id}),
            ),
        )
        if cursor.rowcount:
            counts["claims"] += 1
        claim_entity_id: str | None = (
            entity_ids.get(claim.entity_key) if claim.entity_key else None
        )
        cursor.execute(
            """
            INSERT INTO kc_claim (
              claim_id, entity_id, subject, predicate, object_value, claim_text,
              validation_status, lifecycle_status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, 'SUPPORTED', 'UNRESOLVED', %s::jsonb)
            ON CONFLICT (claim_id) DO NOTHING
            """,
            (
                claim_id,
                claim_entity_id,
                claim.subject,
                claim.predicate,
                claim.object_value,
                claim.claim_text,
                json.dumps(
                    {
                        "lifecycle_proposal": claim.lifecycle_proposal,
                        "confidence": claim.confidence,
                        "processing_fingerprint": processing_fingerprint,
                    }
                ),
            ),
        )
        for anchor in claim.evidence:
            cursor.execute(
                """
                INSERT INTO kc_claim_evidence (
                  claim_id, chunk_id, source_id, revision_id, artifact_id, relation
                ) VALUES (%s, %s, %s, %s, %s, 'supports')
                ON CONFLICT DO NOTHING
                """,
                (
                    claim_id,
                    anchor.chunk_id,
                    anchor.source_id,
                    anchor.revision_id,
                    anchor.artifact_id,
                ),
            )

    for rel in result.relationships:
        from_id = entity_ids.get(rel.from_entity_key)
        to_id = entity_ids.get(rel.to_entity_key)
        if not from_id or not to_id:
            continue
        relationship_id = stable_id("relationship", processing_fingerprint, rel.key)
        cursor.execute(
            """
            INSERT INTO kc_derived_record (
              derived_id, job_id, derived_kind, record_key, processing_fingerprint, payload
            ) VALUES (%s, %s, 'relationship', %s, %s, '{}'::jsonb)
            ON CONFLICT (derived_kind, record_key, processing_fingerprint) DO NOTHING
            """,
            (
                stable_id("derived", job_id, "relationship", rel.key),
                job_id,
                rel.key,
                processing_fingerprint,
            ),
        )
        if cursor.rowcount:
            counts["relationships"] += 1
        cursor.execute(
            """
            INSERT INTO kc_relationship (
              relationship_id, from_entity_id, to_entity_id, relationship_type, metadata
            ) VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (relationship_id) DO NOTHING
            """,
            (
                relationship_id,
                from_id,
                to_id,
                rel.relationship_type,
                json.dumps({"confidence": rel.confidence}),
            ),
        )

    for decision in result.decisions:
        record_key = decision.key
        cursor.execute(
            """
            INSERT INTO kc_derived_record (
              derived_id, job_id, derived_kind, record_key, processing_fingerprint, payload
            ) VALUES (%s, %s, 'decision', %s, %s, %s::jsonb)
            ON CONFLICT (derived_kind, record_key, processing_fingerprint) DO NOTHING
            """,
            (
                stable_id("derived", job_id, "decision", record_key),
                job_id,
                record_key,
                processing_fingerprint,
                json.dumps({"title": decision.title}),
            ),
        )
        if cursor.rowcount:
            counts["decisions"] += 1

    return counts

