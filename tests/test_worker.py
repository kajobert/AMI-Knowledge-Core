from __future__ import annotations

from pathlib import Path

import pytest

from ami_knowledge_core.db import connect
from ami_knowledge_core.extraction.adapter import ExtractionAdapter
from ami_knowledge_core.extraction.contract import EvidenceAnchor, ExtractedClaim, ExtractionResult
from ami_knowledge_core.ingest import ingest_manifest
from ami_knowledge_core.worker import discover_jobs, process_job, run_worker
from ami_knowledge_core.worker import policy as worker_policy


class _BadEvidenceAdapter(ExtractionAdapter):
    adapter_name = "bad-evidence"

    def extract(
        self,
        *,
        source_id: str,
        revision_id: str,
        chunk_evidence: tuple[EvidenceAnchor, ...],
        context: dict | None = None,
    ) -> ExtractionResult:
        return ExtractionResult(
            source_id=source_id,
            revision_id=revision_id,
            claims=(
                ExtractedClaim(
                    key="bad",
                    subject="x",
                    predicate="y",
                    object_value="z",
                    claim_text="bad",
                    evidence=(
                        EvidenceAnchor(
                            source_id=source_id,
                            revision_id=revision_id,
                            artifact_id="missing",
                            chunk_id="kc_chunk_missing",
                        ),
                    ),
                ),
            ),
        )


def test_worker_idempotent_rerun(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    assert discover_jobs(batch_id="archaeology_batch_001") == 8
    first = run_worker(queue_limit=20)
    assert first.succeeded == 8
    second = run_worker(queue_limit=20)
    assert second.processed == 0

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM kc_derived_record")
        derived_count = int(cursor.fetchone()["count"])
        cursor.execute("SELECT COUNT(*) AS count FROM kc_canonical_record")
        canonical_count = int(cursor.fetchone()["count"])
    assert derived_count > 0
    assert canonical_count == 0


def test_fingerprint_change_requeues(
    archaeology_manifest: Path,
    raw_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    discover_jobs(batch_id="archaeology_batch_001")
    run_worker(queue_limit=20)

    monkeypatch.setattr(worker_policy, "EXTRACTION_POLICY_VERSION", "extract-v0.1-changed")
    created = discover_jobs(batch_id="archaeology_batch_001")
    assert created == 8


def test_one_source_failure_isolation(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    discover_jobs(batch_id="archaeology_batch_001")

    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT job_id, revision_id FROM kc_archaeology_job
            ORDER BY job_id LIMIT 1
            """
        )
        row = cursor.fetchone()
        assert row is not None
        cursor.execute("DELETE FROM kc_chunk WHERE revision_id = %s", (row["revision_id"],))
        failing_job_id = row["job_id"]
    assert process_job(str(failing_job_id)) == "ERROR"

    report = run_worker(queue_limit=20)
    assert report.failed == 0
    assert report.succeeded >= 7


def test_invalid_evidence_rejected(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    discover_jobs(batch_id="archaeology_batch_001")
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT job_id FROM kc_archaeology_job LIMIT 1")
        job_id = cursor.fetchone()["job_id"]
    assert process_job(str(job_id), extractor=_BadEvidenceAdapter()) == "ERROR"

