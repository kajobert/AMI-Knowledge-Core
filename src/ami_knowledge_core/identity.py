"""Deterministic identities for idempotent knowledge ingestion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Sequence):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported identity value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a supported value into stable UTF-8 JSON."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_id(namespace: str, *parts: Any, prefix: str = "kc") -> str:
    """Return a deterministic compact identifier from semantic input parts."""

    if not namespace.strip():
        raise ValueError("namespace must not be empty")
    payload = canonical_json({"namespace": namespace, "parts": list(parts)})
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{namespace}_{digest}"


def sha256_text(text: str) -> str:
    """Return the full SHA-256 digest for text content."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
