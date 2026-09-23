from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ami_knowledge_core.archaeology.host_bridge import _coerce_args, _json_safe, dispatch
from ami_knowledge_core.archaeology.scheduler_store import Lease


def test_host_bridge_rejects_unknown_operations() -> None:
    with pytest.raises(ValueError, match="host_bridge_op_not_allowed"):
        dispatch({"op": "arbitrary_sql", "args": {}})


def test_host_bridge_normalizes_iso_time_and_slotted_records() -> None:
    args = _coerce_args({"now": "2026-09-23T12:34:56Z"})
    assert args["now"] == datetime(2026, 9, 23, 12, 34, 56, tzinfo=UTC)

    lease = Lease(
        lease_id="lease-1",
        campaign_id="camp-1",
        work_ref="wr_phase4",
        task_id="task-1",
        slot_id=2,
        attempt=1,
        expires_at=datetime(2026, 9, 23, 12, 35, 56, tzinfo=UTC),
    )
    payload = _json_safe(lease)
    assert payload["lease_id"] == "lease-1"
    assert payload["slot_id"] == 2
    assert payload["expires_at"] == "2026-09-23T12:35:56+00:00"
