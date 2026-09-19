"""Idempotent local-file ingest driven by acquisition manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg

from ..chunking import (
    chunk_markdown,
    chunk_plain_text,
)
from ..db import connect
from ..identity import stable_id
from ..parsers import get_parser
from .manifest import AcquisitionManifest, ManifestEntry, load_manifest


@dataclass(frozen=True, slots=True)
class IngestResult:
    ingest_run_id: str
    manifest_sha256: str
    sources_touched: int
    revisions_created: int
    acquisitions_recorded: int
    chunks_written: int
    idempotent_skips: int


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _store_raw_blob(
    cursor: psycopg.Cursor[Any],
    *,
    content_sha256: str,
    raw_store: Path,
    source_path: Path,
) -> str:
    storage_ref = f"{content_sha256[:2]}/{content_sha256}"
    dest = raw_store / storage_ref
    cursor.execute(
        "SELECT content_sha256 FROM kc_raw_blob WHERE content_sha256 = %s",
        (content_sha256,),
    )
    if cursor.fetchone() is not None:
        return storage_ref
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source_path.read_bytes())
    cursor.execute(
        """
        INSERT INTO kc_raw_blob (content_sha256, byte_length, storage_ref)
        VALUES (%s, %s, %s)
        """,
        (content_sha256, source_path.stat().st_size, storage_ref),
    )
    return storage_ref


def _chunk_document(
    parser_key: str,
    revision_id: str,
    artifact_id: str,
    text: str,
) -> list[Any]:
    if parser_key == "markdown":
        return chunk_markdown(revision_id, artifact_id, text)
    if parser_key == "plain_text":
        return chunk_plain_text(revision_id, artifact_id, text)
    # Parsed but chunked as markdown fallback for unknown structured parsers in v0
    get_parser(parser_key)
    return chunk_markdown(revision_id, artifact_id, text)


def ingest_manifest(
    manifest_path: Path,
    *,
    raw_store: Path,
    ingest_run_id: str | None = None,
) -> IngestResult:
    manifest = load_manifest(manifest_path)
    run_id = ingest_run_id or stable_id(
        "ingest_run",
        manifest.manifest_sha256,
        manifest.batch_id,
        uuid4().hex,
    )
    stats: dict[str, int] = {
        "sources_touched": 0,
        "revisions_created": 0,
        "acquisitions_recorded": 0,
        "chunks_written": 0,
        "idempotent_skips": 0,
    }

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO kc_ingest_run (ingest_run_id, manifest_sha256, status)
                VALUES (%s, %s, 'RUNNING')
                ON CONFLICT (ingest_run_id) DO NOTHING
                """,
                (run_id, manifest.manifest_sha256),
            )

            for entry in manifest.entries:
                _ingest_entry(
                    cursor,
                    manifest=manifest,
                    entry=entry,
                    ingest_run_id=run_id,
                    raw_store=raw_store,
                    stats=stats,
                )

            cursor.execute(
                """
                UPDATE kc_ingest_run
                SET status = 'COMPLETED', finished_at = %s, stats = %s::jsonb
                WHERE ingest_run_id = %s
                """,
                (datetime.now(tz=UTC), json.dumps(stats), run_id),
            )
            cursor.execute(
                """
                INSERT INTO kc_timeline_event (
                  event_id, event_type, ingest_run_id, summary, payload
                ) VALUES (%s, 'INGEST_COMPLETED', %s, %s, %s::jsonb)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    stable_id("timeline", run_id, "completed"),
                    run_id,
                    f"Ingest completed for batch {manifest.batch_id}",
                    json.dumps({"batch_id": manifest.batch_id, "stats": stats}),
                ),
            )
        connection.commit()

    return IngestResult(
        ingest_run_id=run_id,
        manifest_sha256=manifest.manifest_sha256,
        sources_touched=stats["sources_touched"],
        revisions_created=stats["revisions_created"],
        acquisitions_recorded=stats["acquisitions_recorded"],
        chunks_written=stats["chunks_written"],
        idempotent_skips=stats["idempotent_skips"],
    )


def _ingest_entry(
    cursor: psycopg.Cursor[Any],
    *,
    manifest: AcquisitionManifest,
    entry: ManifestEntry,
    ingest_run_id: str,
    raw_store: Path,
    stats: dict[str, int],
) -> None:
    file_path = (manifest.base_dir / entry.file).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"missing ingest file: {file_path}")

    content_sha256 = _sha256_file(file_path)
    source_id = stable_id("source", entry.slug)
    revision_id = stable_id("revision", source_id, content_sha256)
    artifact_id = stable_id("artifact", revision_id, entry.file, entry.parser)
    acquisition_id = stable_id(
        "acquisition",
        ingest_run_id,
        source_id,
        content_sha256,
        entry.provenance,
    )

    _store_raw_blob(
        cursor,
        content_sha256=content_sha256,
        raw_store=raw_store,
        source_path=file_path,
    )

    cursor.execute(
        """
        INSERT INTO kc_source (
          source_id, slug, title, description,
          implementation_status, lifecycle_status, access_class
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id) DO UPDATE SET
          title = EXCLUDED.title,
          description = EXCLUDED.description,
          implementation_status = EXCLUDED.implementation_status,
          lifecycle_status = EXCLUDED.lifecycle_status,
          updated_at = now()
        """,
        (
            source_id,
            entry.slug,
            entry.title,
            entry.description,
            entry.implementation_status.value,
            entry.lifecycle_status.value,
            entry.access_class.value,
        ),
    )
    stats["sources_touched"] += 1

    cursor.execute(
        "SELECT revision_id FROM kc_source_revision WHERE revision_id = %s",
        (revision_id,),
    )
    revision_exists = cursor.fetchone() is not None
    if not revision_exists:
        cursor.execute(
            """
            SELECT COALESCE(MAX(revision_number), 0) + 1 AS revision_number
            FROM kc_source_revision
            WHERE source_id = %s
            """,
            (source_id,),
        )
        count_row = cursor.fetchone()
        assert count_row is not None
        revision_number = int(count_row["revision_number"])
        cursor.execute(
            """
            INSERT INTO kc_source_revision (
              revision_id, source_id, content_sha256, revision_number,
              revision_label, origin, acquired_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                revision_id,
                source_id,
                content_sha256,
                revision_number,
                f"rev-{revision_number}",
                entry.origin,
                datetime.now(tz=UTC),
                json.dumps({"batch_id": manifest.batch_id, "provenance": entry.provenance}),
            ),
        )
        stats["revisions_created"] += 1

    cursor.execute(
        """
        INSERT INTO kc_acquisition (
          acquisition_id, content_sha256, ingest_run_id,
          source_id, revision_id, provenance
        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (acquisition_id) DO NOTHING
        """,
        (
            acquisition_id,
            content_sha256,
            ingest_run_id,
            source_id,
            revision_id,
            json.dumps(entry.provenance),
        ),
    )
    if cursor.rowcount:
        stats["acquisitions_recorded"] += 1

    parser = get_parser(entry.parser)
    parsed = parser.parse(file_path.read_text(encoding="utf-8"), metadata={"slug": entry.slug})

    cursor.execute(
        """
        INSERT INTO kc_artifact (
          artifact_id, revision_id, source_id, media_type,
          relative_path, parser_key, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (artifact_id) DO NOTHING
        """,
        (
            artifact_id,
            revision_id,
            source_id,
            entry.media_type,
            entry.file,
            entry.parser,
            json.dumps({"parser_version": parser.parser_version}),
        ),
    )

    cursor.execute("SELECT COUNT(*) AS count FROM kc_chunk WHERE artifact_id = %s", (artifact_id,))
    chunk_row = cursor.fetchone()
    assert chunk_row is not None
    existing_chunks = int(chunk_row["count"])
    if existing_chunks:
        stats["idempotent_skips"] += 1
        return

    chunks = _chunk_document(entry.parser, revision_id, artifact_id, parsed.text)
    for chunk in chunks:
        cursor.execute(
            """
            INSERT INTO kc_chunk (
              chunk_id, artifact_id, revision_id, ordinal,
              content_sha256, chunker_version, text_content, anchor
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                chunk.chunk_id,
                artifact_id,
                revision_id,
                chunk.ordinal,
                chunk.content_sha256,
                chunk.chunker_version,
                chunk.text,
                json.dumps(
                    {
                        "heading_path": list(chunk.heading_path),
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                    }
                ),
            ),
        )
        stats["chunks_written"] += 1

