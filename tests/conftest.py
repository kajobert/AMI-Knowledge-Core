from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from ami_knowledge_core.migrate import apply_migrations

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFEST = ROOT / "fixtures/archaeology_batch_001.manifest.json"


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture(scope="session", autouse=True)
def migrated_schema(database_url: str) -> None:
    apply_migrations()


@pytest.fixture
def raw_store(tmp_path: Path) -> Path:
    store = tmp_path / "raw"
    store.mkdir()
    return store


@pytest.fixture
def archaeology_manifest() -> Path:
    return FIXTURE_MANIFEST


@pytest.fixture(autouse=True)
def clean_tables(database_url: str) -> Iterator[None]:
    import psycopg

    tables = [
        "kc_synthesis_proposal",
        "kc_derived_record",
        "kc_archaeology_job",
        "kc_worker_run",
        "kc_timeline_event",
        "kc_canonical_record",
        "kc_conflict",
        "kc_relationship",
        "kc_claim_evidence",
        "kc_claim",
        "kc_entity_alias",
        "kc_entity",
        "kc_chunk",
        "kc_artifact",
        "kc_acquisition",
        "kc_source_revision",
        "kc_source",
        "kc_raw_blob",
        "kc_ingest_run",
    ]
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"TRUNCATE {table} CASCADE")
        connection.commit()
    yield

