"""Processing fingerprint for idempotent archaeology reruns."""

from __future__ import annotations

from typing import Any

import psycopg

from ..identity import sha256_text, stable_id
from . import policy


def compute_processing_fingerprint(
    *,
    revision_content_sha256: str,
    parser_versions: tuple[str, ...],
) -> str:
    payload = {
        "source_revision_hash": revision_content_sha256,
        "parser_versions": sorted(parser_versions),
        "extraction_policy_version": policy.EXTRACTION_POLICY_VERSION,
        "router_model_policy_version": policy.ROUTER_MODEL_POLICY_VERSION,
        "canonical_context_hash": policy.CANONICAL_CONTEXT_HASH,
    }
    return stable_id("processing_fingerprint", payload)


def parser_versions_for_revision(cursor: psycopg.Cursor[Any], revision_id: str) -> tuple[str, ...]:
    cursor.execute(
        """
        SELECT DISTINCT coalesce(metadata->>'parser_version', parser_key) AS parser_version
        FROM kc_artifact
        WHERE revision_id = %s
        ORDER BY 1
        """,
        (revision_id,),
    )
    return tuple(str(row["parser_version"]) for row in cursor.fetchall())


def fingerprint_for_revision(cursor: psycopg.Cursor[Any], revision_id: str) -> str:
    cursor.execute(
        "SELECT content_sha256 FROM kc_source_revision WHERE revision_id = %s",
        (revision_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"unknown revision_id: {revision_id}")
    parser_versions = parser_versions_for_revision(cursor, revision_id)
    return compute_processing_fingerprint(
        revision_content_sha256=str(row["content_sha256"]),
        parser_versions=parser_versions,
    )


def fingerprint_changed(
    cursor: psycopg.Cursor[Any],
    *,
    revision_id: str,
    existing_fingerprint: str,
) -> bool:
    return fingerprint_for_revision(cursor, revision_id) != existing_fingerprint


def fingerprint_audit_hash(fingerprint: str) -> str:
    return sha256_text(fingerprint)

