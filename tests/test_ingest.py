from __future__ import annotations

from pathlib import Path

import psycopg

from ami_knowledge_core.ingest import ingest_manifest


def test_ingest_idempotent_and_acquisitions(
    database_url: str,
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    first = ingest_manifest(archaeology_manifest, raw_store=raw_store)
    second = ingest_manifest(archaeology_manifest, raw_store=raw_store)

    assert first.sources_touched == 8
    assert first.chunks_written > 0
    assert second.idempotent_skips >= 8
    assert second.chunks_written == 0

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM kc_raw_blob")
        blob_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM kc_acquisition")
        acquisition_count = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(DISTINCT content_sha256) FROM kc_acquisition"
        )
        distinct_hashes = int(cursor.fetchone()[0])

    assert blob_count == 8
    assert acquisition_count == 16
    assert distinct_hashes == 8


def test_sha_duplicate_detection(database_url: str, raw_store: Path, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    content_dir = tmp_path / "synthetic"
    content_dir.mkdir()
    shared = content_dir / "shared.md"
    shared.write_text("# Shared\nSame body.\n", encoding="utf-8")

    manifest.write_text(
        """
{
  "manifest_version": "1",
  "batch_id": "dup-test",
  "entries": [
    {
      "slug": "source-a",
      "title": "A",
      "file": "synthetic/shared.md",
      "parser": "markdown",
      "implementation_status": "UNKNOWN",
      "lifecycle_status": "UNRESOLVED",
      "provenance": {"copy": 1}
    },
    {
      "slug": "source-b",
      "title": "B",
      "file": "synthetic/shared.md",
      "parser": "markdown",
      "implementation_status": "UNKNOWN",
      "lifecycle_status": "UNRESOLVED",
      "provenance": {"copy": 2}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    ingest_manifest(manifest, raw_store=raw_store)

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM kc_raw_blob")
        assert int(cursor.fetchone()[0]) == 1
        cursor.execute("SELECT COUNT(*) FROM kc_source_revision")
        assert int(cursor.fetchone()[0]) == 2

