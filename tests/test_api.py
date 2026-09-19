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


def test_encyclopedia_ui_contract(
    client: TestClient,
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)

    matrix = client.get("/api/reality-matrix").json()
    assert len(matrix) == 8
    assert {"matrix_status", "supporting_evidence", "source_id"}.issubset(matrix[0].keys())

    graph = client.get(
        "/api/graph",
        params={"root": "batch:archaeology_batch_001", "depth": 1},
    ).json()
    assert any(node["kind"] == "source" for node in graph["nodes"])

    unified = client.get("/api/search", params={"q": "Sophia"}).json()
    assert unified["sources"]

    source_id = matrix[0]["source_id"]
    inspected = client.get(f"/api/inspect/source/{source_id}").json()
    assert inspected["kind"] == "source"
    assert inspected["chain"]

