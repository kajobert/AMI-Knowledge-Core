from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from ami_knowledge_core.amica_adapter import (
    AdapterLimits,
    KnowledgeCoreConnectionError,
    KnowledgeCoreReadAdapter,
    KnowledgeCoreTimeoutError,
    KnowledgeCoreUnavailableError,
)
from ami_knowledge_core.api.app import app
from ami_knowledge_core.ingest import ingest_manifest


class _TestClientTransport(httpx.BaseTransport):
    def __init__(self, test_client: TestClient) -> None:
        self._test_client = test_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query.decode()}"
        response = self._test_client.request(request.method, path)
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return httpx.Response(response.status_code, json=response.json())
        return httpx.Response(response.status_code, content=response.content)


def test_adapter_search_and_limits(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    test_client = TestClient(app)
    adapter = KnowledgeCoreReadAdapter(
        "http://testserver",
        limits=AdapterLimits(search_limit=5, timeout_seconds=2.0),
        transport=_TestClientTransport(test_client),
    )
    health = adapter.health()
    assert health["status"] == "ok"
    results = adapter.search("Sophia")
    assert len(results["sources"]) <= 5
    sources = adapter.list_sources(current=False)
    assert sources
    graph = adapter.graph_neighborhood(root="batch:archaeology_batch_001", depth=1)
    assert graph["nodes"]


def test_adapter_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SlowTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("slow")

    adapter = KnowledgeCoreReadAdapter(
        "http://example.invalid",
        limits=AdapterLimits(timeout_seconds=0.01),
        transport=_SlowTransport(),
    )
    with pytest.raises(KnowledgeCoreTimeoutError):
        adapter.health()


def test_adapter_unavailable() -> None:
    class _FailTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "down"})

    adapter = KnowledgeCoreReadAdapter(
        "http://example.invalid",
        transport=_FailTransport(),
    )
    with pytest.raises(KnowledgeCoreUnavailableError):
        adapter.health()


def test_adapter_connection_error() -> None:
    adapter = KnowledgeCoreReadAdapter("http://127.0.0.1:1")
    with pytest.raises(KnowledgeCoreConnectionError):
        adapter.health()

