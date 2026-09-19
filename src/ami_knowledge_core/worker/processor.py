"""Per-source archaeology worker with isolated transactions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

import psycopg

from ..db import database_url
from ..extraction.adapter import ExtractionAdapter, HeuristicExtractionAdapter
from ..extraction.apply import apply_extraction
from ..extraction.contract import EvidenceAnchor, ExtractionResult
from ..extraction.validate import ExtractionValidationError, validate_extraction_result
from ..identity import stable_id
from ..synthesis.apply import apply_synthesis_proposals
from ..synthesis.contract import AlignmentClass, SynthesisProposal
from .fingerprint import fingerprint_for_revision

JobState = Literal[
    "DISCOVERED",
    "ACQUIRED",
    "PARSED",
    "EXTRACTION_PENDING",
    "EXTRACTED",
    "SYNTHESIS_PENDING",
    "REVIEW_PENDING",
    "ERROR",
    "RETRY_PENDING",
]

STATE_ORDER: tuple[JobState, ...] = (
    "DISCOVERED",
    "ACQUIRED",
    "PARSED",
    "EXTRACTION_PENDING",
    "EXTRACTED",
    "SYNTHESIS_PENDING",
    "REVIEW_PENDING",
)


@dataclass(frozen=True, slots=True)
class WorkerRunReport:
    worker_run_id: str
    processed: int
    succeeded: int
    failed: int
    skipped: int


def _update_job_state(
    cursor: psycopg.Cursor[Any],
    *,
    job_id: str,
    state: JobState,
    checkpoint: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    increment_attempt = 1 if error else 0
    cursor.execute(
        """
        UPDATE kc_archaeology_job
        SET state = %s,
            updated_at = %s,
            checkpoint = coalesce(%s::jsonb, checkpoint),
            last_error = %s,
            attempt_count = attempt_count + %s
        WHERE job_id = %s
        """,
        (
            state,
            datetime.now(tz=UTC),
            json.dumps(checkpoint) if checkpoint is not None else None,
            error,
            increment_attempt,
            job_id,
        ),
    )


def _load_job(cursor: psycopg.Cursor[Any], job_id: str) -> dict[str, Any]:
    cursor.execute("SELECT * FROM kc_archaeology_job WHERE job_id = %s", (job_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"unknown job_id: {job_id}")
    return dict(row)


def _chunk_anchors(cursor: psycopg.Cursor[Any], revision_id: str) -> tuple[EvidenceAnchor, ...]:
    cursor.execute(
        """
        SELECT c.chunk_id, c.revision_id, c.artifact_id, a.source_id
        FROM kc_chunk c
        JOIN kc_artifact a ON a.artifact_id = c.artifact_id
        WHERE c.revision_id = %s
        ORDER BY c.ordinal
        LIMIT 20
        """,
        (revision_id,),
    )
    return tuple(
        EvidenceAnchor(
            source_id=row["source_id"],
            revision_id=row["revision_id"],
            artifact_id=row["artifact_id"],
            chunk_id=row["chunk_id"],
        )
        for row in cursor.fetchall()
    )


def _build_synthesis(
    *,
    source_id: str,
    revision_id: str,
    source_row: dict[str, Any],
    extraction: ExtractionResult,
) -> tuple[SynthesisProposal, ...]:
    lifecycle = str(source_row.get("lifecycle_status", "UNRESOLVED"))
    impl = str(source_row.get("implementation_status", "UNKNOWN"))
    if lifecycle == "CURRENT" and impl in {"IMPLEMENTED", "VALIDATED"}:
        classification = "CURRENT"
    elif lifecycle == "HISTORICAL":
        classification = "HISTORICAL"
    elif lifecycle == "SUPERSEDED":
        classification = "SUPERSEDED"
    elif lifecycle == "CURRENT":
        classification = "PARTIAL"
    else:
        classification = "UNRESOLVED"

    supporting: list[dict[str, str]] = []
    for claim in extraction.claims:
        for anchor in claim.evidence:
            supporting.append({"chunk_id": anchor.chunk_id, "claim_key": claim.key})

    return (
        SynthesisProposal(
            key=f"synthesis:{revision_id}",
            source_id=source_id,
            revision_id=revision_id,
            classification=cast(AlignmentClass, classification),
            summary=(
                f"Alignment proposal for {source_row.get('slug', source_id)} "
                f"({lifecycle}/{impl}) — review required."
            ),
            supporting_evidence=tuple(supporting),
            opposing_evidence=(),
            confidence=0.5,
            metadata={"auto_generated": True, "review_required": True},
        ),
    )


def process_job(
    job_id: str,
    *,
    extractor: ExtractionAdapter | None = None,
) -> JobState:
    adapter = extractor or HeuristicExtractionAdapter()

    with psycopg.connect(database_url()) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            job = _load_job(cursor, job_id)
            if job["state"] == "REVIEW_PENDING":
                return "REVIEW_PENDING"

            source_id = str(job["source_id"])
            revision_id = str(job["revision_id"])
            fingerprint = str(job["processing_fingerprint"])

            cursor.execute("SELECT * FROM kc_source WHERE source_id = %s", (source_id,))
            source_row = cursor.fetchone()
            if source_row is None:
                _update_job_state(cursor, job_id=job_id, state="ERROR", error="missing source")
                connection.commit()
                return "ERROR"

            extraction_cache: ExtractionResult | None = None
            try:
                while True:
                    job = _load_job(cursor, job_id)
                    current = str(job["state"])
                    if current == "REVIEW_PENDING":
                        return "REVIEW_PENDING"
                    if current == "ERROR":
                        return "ERROR"

                    if current in {"DISCOVERED", "RETRY_PENDING"}:
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="ACQUIRED",
                            checkpoint={"step": "acquired"},
                        )
                        connection.commit()
                        continue

                    if current == "ACQUIRED":
                        anchors = _chunk_anchors(cursor, revision_id)
                        if not anchors:
                            raise RuntimeError("no parsed chunks for revision")
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="PARSED",
                            checkpoint={"step": "parsed", "chunk_count": len(anchors)},
                        )
                        connection.commit()
                        continue

                    if current == "PARSED":
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="EXTRACTION_PENDING",
                            checkpoint={"step": "extraction_pending"},
                        )
                        connection.commit()
                        continue

                    if current == "EXTRACTION_PENDING":
                        anchors = _chunk_anchors(cursor, revision_id)
                        extraction_cache = adapter.extract(
                            source_id=source_id,
                            revision_id=revision_id,
                            chunk_evidence=anchors,
                            context={"slug": source_row["slug"]},
                        )
                        validate_extraction_result(cursor, extraction_cache)
                        apply_extraction(
                            cursor,
                            job_id=job_id,
                            processing_fingerprint=fingerprint,
                            result=extraction_cache,
                        )
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="EXTRACTED",
                            checkpoint={"step": "extracted"},
                        )
                        connection.commit()
                        continue

                    if current == "EXTRACTED":
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="SYNTHESIS_PENDING",
                            checkpoint={"step": "synthesis_pending"},
                        )
                        connection.commit()
                        continue

                    if current == "SYNTHESIS_PENDING":
                        if extraction_cache is None:
                            anchors = _chunk_anchors(cursor, revision_id)
                            extraction_cache = adapter.extract(
                                source_id=source_id,
                                revision_id=revision_id,
                                chunk_evidence=anchors,
                                context={"slug": source_row["slug"]},
                            )
                        proposals = _build_synthesis(
                            source_id=source_id,
                            revision_id=revision_id,
                            source_row=dict(source_row),
                            extraction=extraction_cache,
                        )
                        apply_synthesis_proposals(
                            cursor,
                            job_id=job_id,
                            processing_fingerprint=fingerprint,
                            proposals=proposals,
                        )
                        _update_job_state(
                            cursor,
                            job_id=job_id,
                            state="REVIEW_PENDING",
                            checkpoint={"step": "review_pending"},
                        )
                        connection.commit()
                        return "REVIEW_PENDING"

                    raise RuntimeError(f"unsupported job state: {current}")

            except (ExtractionValidationError, RuntimeError, ValueError) as exc:
                _update_job_state(cursor, job_id=job_id, state="ERROR", error=str(exc))
                connection.commit()
                return "ERROR"

    return "REVIEW_PENDING"


def run_worker(
    *,
    queue_limit: int = 20,
    extractor: ExtractionAdapter | None = None,
) -> WorkerRunReport:
    worker_run_id = stable_id("worker_run", uuid4().hex)
    processed = succeeded = failed = skipped = 0

    with psycopg.connect(database_url()) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO kc_worker_run (worker_run_id, status, queue_limit)
                VALUES (%s, 'RUNNING', %s)
                """,
                (worker_run_id, queue_limit),
            )
            cursor.execute(
                """
                SELECT job_id, state
                FROM kc_archaeology_job
                WHERE state IN ('DISCOVERED', 'RETRY_PENDING')
                ORDER BY updated_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (queue_limit,),
            )
            jobs = list(cursor.fetchall())
        connection.commit()

    for job in jobs:
        processed += 1
        final_state = process_job(str(job["job_id"]), extractor=extractor)
        if final_state == "REVIEW_PENDING":
            succeeded += 1
        elif final_state == "ERROR":
            failed += 1
        else:
            skipped += 1

    stats = {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
    }
    with psycopg.connect(database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE kc_worker_run
                SET status = %s, finished_at = %s, stats = %s::jsonb
                WHERE worker_run_id = %s
                """,
                (
                    "COMPLETED" if failed == 0 else "FAILED",
                    datetime.now(tz=UTC),
                    json.dumps(stats),
                    worker_run_id,
                ),
            )
        connection.commit()

    return WorkerRunReport(
        worker_run_id=worker_run_id,
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
    )


def discover_jobs(*, batch_id: str | None = None) -> int:
    created = 0
    with psycopg.connect(database_url()) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT r.revision_id, r.source_id, r.metadata, s.slug
                FROM kc_source_revision r
                JOIN kc_source s ON s.source_id = r.source_id
                ORDER BY s.slug, r.revision_number
                """
            )
            for row in cursor.fetchall():
                metadata = row.get("metadata") or {}
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                if batch_id and metadata.get("batch_id") != batch_id:
                    continue
                fingerprint = fingerprint_for_revision(cursor, str(row["revision_id"]))
                job_id = stable_id("arch_job", row["revision_id"], fingerprint)
                cursor.execute(
                    """
                    INSERT INTO kc_archaeology_job (
                      job_id, source_id, revision_id, state, processing_fingerprint
                    ) VALUES (%s, %s, %s, 'DISCOVERED', %s)
                    ON CONFLICT (revision_id, processing_fingerprint) DO NOTHING
                    """,
                    (
                        job_id,
                        row["source_id"],
                        row["revision_id"],
                        fingerprint,
                    ),
                )
                if cursor.rowcount:
                    created += 1
        connection.commit()
    return created

