from __future__ import annotations


class KnowledgeCoreAdapterError(Exception):
    pass


class KnowledgeCoreTimeoutError(KnowledgeCoreAdapterError):
    pass


class KnowledgeCoreConnectionError(KnowledgeCoreAdapterError):
    pass


class KnowledgeCoreUnavailableError(KnowledgeCoreAdapterError):
    pass


class KnowledgeCoreHTTPError(KnowledgeCoreAdapterError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"HTTP {status_code}: {body[:200]}")
        self.status_code = status_code
        self.body = body

