from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ami_knowledge_core.api.app import app
from ami_knowledge_core.ingest import ingest_manifest


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["pgvector"] != "missing"


def test_read_only_sources_and_claim_chain(
    client: TestClient,
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    sources = client.get("/api/sources").json()
    assert len(sources) == 8
    detail = client.get(f"/api/sources/{sources[0]['source_id']}").json()
    assert "revisions" in detail
    search = client.get("/api/chunks/search", params={"q": "Knowledge"}).json()
    assert isinstance(search, list)

