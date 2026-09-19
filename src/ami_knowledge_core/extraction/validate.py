"""Validate extraction payloads against provenance IDs."""

from __future__ import annotations

from typing import Any

import psycopg

from .contract import EvidenceAnchor, ExtractionResult


class ExtractionValidationError(ValueError):
    pass


def _anchor_exists(cursor: psycopg.Cursor[Any], anchor: EvidenceAnchor) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM kc_chunk c
        JOIN kc_artifact a ON a.artifact_id = c.artifact_id
        JOIN kc_source_revision r ON r.revision_id = c.revision_id
        WHERE c.chunk_id = %s
          AND a.artifact_id = %s
          AND r.revision_id = %s
          AND a.source_id = %s
        """,
        (anchor.chunk_id, anchor.artifact_id, anchor.revision_id, anchor.source_id),
    )
    return cursor.fetchone() is not None


def validate_extraction_result(cursor: psycopg.Cursor[Any], result: ExtractionResult) -> None:
    anchors: list[EvidenceAnchor] = []
    for claim in result.claims:
        anchors.extend(claim.evidence)
    for decision in result.decisions:
        anchors.extend(decision.evidence)

    for anchor in anchors:
        if not _anchor_exists(cursor, anchor):
            raise ExtractionValidationError(
                f"unknown evidence anchor chunk_id={anchor.chunk_id}"
            )

