"""Deterministic no-network Phase 2 backend simulator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..identity import canonical_json


@dataclass(frozen=True, slots=True)
class SimulatedResult:
    status: str
    output_hash: str
    payload: dict[str, object]


def run_simulated_task(
    *,
    task_id: str,
    attempt: int,
    policy_bundle_hash: str,
) -> SimulatedResult:
    payload = {
        "task_id": task_id,
        "attempt": attempt,
        "policy_bundle_hash": policy_bundle_hash,
        "backend": "deterministic-simulator-v1",
        "result": "SIMULATED_OK",
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return SimulatedResult(status="SUCCESS", output_hash=digest, payload=payload)
