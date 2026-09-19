from __future__ import annotations

from pathlib import Path

import pytest

from ami_knowledge_core.contracts import EvidenceRef
from ami_knowledge_core.ingest import ingest_manifest
from ami_knowledge_core.provenance import (
    ClaimDraft,
    ProvenanceError,
    insert_claim,
    promote_canonical_record,
    validate_claim_draft,
)


def test_invalid_provenance_rejection(archaeology_manifest: Path, raw_store: Path) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    draft = ClaimDraft(
        subject="AMI",
        predicate="has_layer",
        object_value="Knowledge Core",
        claim_text="AMI owns Knowledge Core storage.",
        entity_id=None,
        evidence=(
            EvidenceRef(
                source_id="kc_source_missing",
                revision_id="kc_revision_missing",
                artifact_id="kc_artifact_missing",
                chunk_id="kc_chunk_missing",
            ),
        ),
    )
    with pytest.raises(ProvenanceError):
        validate_claim_draft(draft)


def test_claim_evidence_integrity(archaeology_manifest: Path, raw_store: Path) -> None:
    from ami_knowledge_core.db import connect

    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT c.chunk_id, c.artifact_id, c.revision_id, a.source_id
                FROM kc_chunk c
                JOIN kc_artifact a ON a.artifact_id = c.artifact_id
                LIMIT 1
                """
        )
        row = cursor.fetchone()
    assert row is not None
    draft = ClaimDraft(
        subject="Sophia",
        predicate="is",
        object_value="companion entity",
        claim_text="Sophia is a companion entity in AMI ecosystem.",
        entity_id=None,
        evidence=(
            EvidenceRef(
                source_id=row["source_id"],
                revision_id=row["revision_id"],
                artifact_id=row["artifact_id"],
                chunk_id=row["chunk_id"],
            ),
        ),
        validation_status="VALIDATED",
    )
    claim_id = insert_claim(draft)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT validation_status FROM kc_claim WHERE claim_id = %s",
            (claim_id,),
        )
        status = cursor.fetchone()["validation_status"]
        cursor.execute(
            "SELECT COUNT(*) AS count FROM kc_canonical_record WHERE promoted_by = 'llm'"
        )
        canonical_llm = int(cursor.fetchone()["count"])
    assert status == "SUPPORTED"
    assert canonical_llm == 0


def test_no_automatic_canonical_promotion(archaeology_manifest: Path, raw_store: Path) -> None:
    from ami_knowledge_core.db import connect

    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT claim_id FROM kc_claim LIMIT 1")
        if cursor.fetchone() is None:
            pytest.skip("no claims seeded")
    with pytest.raises(ProvenanceError):
        promote_canonical_record(
            canonical_id="kc_canonical_test",
            record_type="decision",
            title="Auto",
            body={"text": "x"},
            supporting_claim_ids=["kc_missing"],
            opposing_claim_ids=[],
            promoted_by="llm",
        )

