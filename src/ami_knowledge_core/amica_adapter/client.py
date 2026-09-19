"""Read-only Amica/OpenClaw client for Knowledge Core HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

from .errors import (
    KnowledgeCoreConnectionError,
    KnowledgeCoreHTTPError,
    KnowledgeCoreTimeoutError,
    KnowledgeCoreUnavailableError,
)


@dataclass(frozen=True, slots=True)
class AdapterLimits:
    search_limit: int = 15
    graph_depth_max: int = 3
    timeout_seconds: float = 5.0


class KnowledgeCoreReadAdapter:
    """Narrow read-only adapter — no SQL, no writes, no filesystem."""

    def __init__(
        self,
        base_url: str,
        *,
        limits: AdapterLimits | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limits = limits or AdapterLimits()
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._limits.timeout_seconds,
            transport=self._transport,
        )

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        client = self._client()
        try:
            response = client.request(method, path, params=params)
        except httpx.TimeoutException as exc:
            raise KnowledgeCoreTimeoutError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise KnowledgeCoreConnectionError(str(exc)) from exc
        finally:
            client.close()

        if response.status_code >= 500:
            raise KnowledgeCoreUnavailableError(
                f"Knowledge Core unavailable: HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise KnowledgeCoreHTTPError(response.status_code, response.text)
        return response.json()

    def health(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/health"))

    def status(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/api/worker/status"))

    def search(self, query: str) -> dict[str, Any]:
        limit = min(self._limits.search_limit, 50)
        return cast(
            dict[str, Any],
            self._request("GET", "/api/search", params={"q": query, "limit": limit}),
        )

    def source_detail(self, source_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/api/sources/{source_id}"))

    def revision_detail(self, source_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._request("GET", f"/api/sources/{source_id}/revisions"),
        )

    def claim_detail(self, claim_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/api/claims/{claim_id}"))

    def evidence_chain(self, claim_id: str) -> dict[str, Any]:
        payload = self.claim_detail(claim_id)
        return {"claim": payload.get("claim"), "evidence": payload.get("evidence", [])}

    def list_sources(
        self,
        *,
        current: bool | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if current is True:
            params["current"] = True
        elif current is False:
            params["current"] = False
        return cast(
            list[dict[str, Any]],
            self._request("GET", "/api/sources", params=params or None),
        )

    def list_conflicts(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/api/conflicts"))

    def graph_neighborhood(
        self,
        *,
        root: str,
        depth: int | None = None,
    ) -> dict[str, Any]:
        depth_value = min(depth or 1, self._limits.graph_depth_max)
        return cast(
            dict[str, Any],
            self._request(
                "GET",
                "/api/graph",
                params={"root": root, "depth": depth_value},
            ),
        )

    def inspect(
        self,
        kind: Literal["source", "revision", "chunk", "claim", "entity"],
        object_id: str,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("GET", f"/api/inspect/{kind}/{object_id}"),
        )

