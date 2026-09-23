"""Host-local JSON bridge for Control Plane-owned archaeology scheduling.

This is deliberately a CLI/stdin surface, not HTTP or MCP. It exposes only the
bounded scheduler-store operations needed by Phase 4.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from .internal_service import ArchaeologyInternalService
from .scheduler_store import (
    configure_task_execution,
    count_active_leases,
    get_campaign,
    get_task,
    record_run_result,
    record_run_start,
    recover_expired_leases,
)

_ALLOWED_OPS = frozenset(
    {
        "get_campaign",
        "recover_expired_leases",
        "count_active_leases",
        "configure_task_execution",
        "acquire_next_lease",
        "get_task",
        "record_run_start",
        "record_run_result",
        "complete_lease",
    }
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return value


def _coerce_args(args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    raw_now = normalized.get("now")
    if isinstance(raw_now, str):
        normalized["now"] = datetime.fromisoformat(raw_now.replace("Z", "+00:00"))
    return normalized


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    op = str(request.get("op", "")).strip()
    if op not in _ALLOWED_OPS:
        raise ValueError("host_bridge_op_not_allowed")
    args = request.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("host_bridge_args_invalid")
    args = _coerce_args(args)

    service = ArchaeologyInternalService()
    result: Any

    if op == "get_campaign":
        result = get_campaign(**args)
    elif op == "recover_expired_leases":
        result = recover_expired_leases(**args)
    elif op == "count_active_leases":
        result = count_active_leases(**args)
    elif op == "configure_task_execution":
        result = configure_task_execution(**args)
    elif op == "acquire_next_lease":
        lease = service.acquire_next_lease(**args)
        result = None if lease is None else _json_safe(lease)
    elif op == "get_task":
        result = get_task(**args)
    elif op == "record_run_start":
        result = record_run_start(**args)
    elif op == "record_run_result":
        result = record_run_result(**args)
    else:
        result = service.complete_lease(**args)

    return {"ok": True, "result": _json_safe(result)}


def main() -> None:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("host_bridge_request_invalid")
        response = dispatch(request)
    except Exception as exc:  # fail closed; never expose stack or environment
        response = {
            "ok": False,
            "error": str(exc) if isinstance(exc, ValueError) else exc.__class__.__name__,
        }
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
