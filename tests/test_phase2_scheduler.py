from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ami_knowledge_core.archaeology.campaign import (
    register_campaign,
    register_corpus_snapshot,
)
from ami_knowledge_core.archaeology.scheduler_store import (
    acquire_next_lease,
    cancel_campaign_tasks,
    complete_lease,
    register_shard,
    register_task,
    upsert_coverage,
)
from ami_knowledge_core.archaeology.simulator import run_simulated_task
from ami_knowledge_core.db import connect
from ami_knowledge_core.ingest import ingest_manifest


WORK_REF = "wr_phase2scheduler0000001"


def _seed_campaign(
    archaeology_manifest: Path,
    raw_store: Path,
    *,
    slot_limit: int = 3,
) -> tuple[str, str, str, str]:
    ingest_manifest(archaeology_manifest, raw_store=raw_store)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT r.revision_id, r.source_id
            FROM kc_source_revision r
            ORDER BY r.revision_id
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    assert row is not None

    revision_id = str(row["revision_id"])
    source_id = str(row["source_id"])
    snapshot_id = register_corpus_snapshot(
        revision_refs=(revision_id,),
        source_registry_version="source-registry-v1",
        parser_policy_version="parser-policy-v1",
        sensitivity_policy_version="sensitivity-policy-v1",
    )
    campaign_id = register_campaign(
        work_ref=WORK_REF,
        corpus_snapshot_id=snapshot_id,
        campaign_version="phase2-v1",
        policy_bundle_hash="phase2-policy-v1",
        slot_limit=slot_limit,
    ).campaign_id
    return campaign_id, snapshot_id, source_id, revision_id


def _seed_tasks(
    archaeology_manifest: Path,
    raw_store: Path,
    *,
    task_count: int,
    slot_limit: int = 3,
) -> tuple[str, list[str]]:
    campaign_id, _, source_id, revision_id = _seed_campaign(
        archaeology_manifest,
        raw_store,
        slot_limit=slot_limit,
    )
    shard_id = register_shard(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        source_id=source_id,
        revision_id=revision_id,
        source_span={"type": "text", "start_byte": 0, "end_byte": 10},
        chunk_refs=(),
        partitioner_version="partitioner-v1",
        eligible_domain_tags=("SYSTEM_ARCHITECTURE",),
        sensitivity_class="PRIVATE_PROJECT",
    )
    upsert_coverage(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        shard_id=shard_id,
        domain_lens="SYSTEM_ARCHITECTURE",
    )
    task_ids = []
    for index in range(task_count):
        task_ids.append(
            register_task(
                campaign_id=campaign_id,
                work_ref=WORK_REF,
                task_kind=f"DOMAIN_EXTRACTION_{index}",
                role="ARCHAEOLOGY_EXTRACTOR",
                target_shard_id=shard_id,
                domain_tags=("SYSTEM_ARCHITECTURE",),
                input_contract_version="phase2-input-v1",
                output_contract_version="phase2-output-v1",
                privacy_class="PRIVATE_PROJECT",
                required_capabilities=("structured_analysis",),
                policy_bundle_hash="phase2-policy-v1",
            )
        )
    return campaign_id, task_ids


def test_shard_task_and_coverage_replay_are_idempotent(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    campaign_id, _, source_id, revision_id = _seed_campaign(
        archaeology_manifest,
        raw_store,
    )
    kwargs = dict(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        source_id=source_id,
        revision_id=revision_id,
        source_span={"type": "text", "start_byte": 0, "end_byte": 10},
        chunk_refs=(),
        partitioner_version="partitioner-v1",
        eligible_domain_tags=("SYSTEM_ARCHITECTURE",),
        sensitivity_class="PRIVATE_PROJECT",
    )
    shard_a = register_shard(**kwargs)
    shard_b = register_shard(**kwargs)
    assert shard_a == shard_b

    task_kwargs = dict(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        task_kind="DOMAIN_EXTRACTION",
        role="ARCHAEOLOGY_EXTRACTOR",
        target_shard_id=shard_a,
        domain_tags=("SYSTEM_ARCHITECTURE",),
        input_contract_version="phase2-input-v1",
        output_contract_version="phase2-output-v1",
        privacy_class="PRIVATE_PROJECT",
        required_capabilities=("structured_analysis",),
        policy_bundle_hash="phase2-policy-v1",
    )
    assert register_task(**task_kwargs) == register_task(**task_kwargs)

    coverage_a = upsert_coverage(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        shard_id=shard_a,
        domain_lens="SYSTEM_ARCHITECTURE",
    )
    coverage_b = upsert_coverage(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        shard_id=shard_a,
        domain_lens="SYSTEM_ARCHITECTURE",
        status="SCHEDULED",
    )
    assert coverage_a == coverage_b


def test_slot_limit_is_hard_ceiling(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    campaign_id, _ = _seed_tasks(
        archaeology_manifest,
        raw_store,
        task_count=6,
        slot_limit=3,
    )
    leases = [
        acquire_next_lease(
            campaign_id=campaign_id,
            work_ref=WORK_REF,
            role="ARCHAEOLOGY_EXTRACTOR",
            backend="deterministic-simulator-v1",
        )
        for _ in range(4)
    ]
    assert [lease.slot_id for lease in leases[:3] if lease is not None] == [1, 2, 3]
    assert leases[3] is None


def test_concurrent_claimers_never_duplicate_task_or_slot(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    campaign_id, _ = _seed_tasks(
        archaeology_manifest,
        raw_store,
        task_count=8,
        slot_limit=5,
    )

    def claim() -> object:
        return acquire_next_lease(
            campaign_id=campaign_id,
            work_ref=WORK_REF,
            role="ARCHAEOLOGY_EXTRACTOR",
            backend="deterministic-simulator-v1",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        leases = [lease for lease in executor.map(lambda _: claim(), range(8)) if lease]

    assert len(leases) == 5
    assert len({lease.task_id for lease in leases}) == 5
    assert len({lease.slot_id for lease in leases}) == 5
    assert max(lease.slot_id for lease in leases) <= 5


def test_expired_lease_recovers_and_old_owner_cannot_complete(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    campaign_id, task_ids = _seed_tasks(
        archaeology_manifest,
        raw_store,
        task_count=1,
        slot_limit=1,
    )
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    old = acquire_next_lease(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        role="ARCHAEOLOGY_EXTRACTOR",
        backend="deterministic-simulator-v1",
        lease_seconds=10,
        now=t0,
    )
    assert old is not None
    replacement = acquire_next_lease(
        campaign_id=campaign_id,
        work_ref=WORK_REF,
        role="ARCHAEOLOGY_EXTRACTOR",
        backend="deterministic-simulator-v1",
        lease_seconds=10,
        now=t0 + timedelta(seconds=11),
    )
    assert replacement is not None
    assert replacement.task_id == task_ids[0]
    assert replacement.lease_id != old.lease_id
    assert replacement.attempt == 2

    assert not complete_lease(
        old.lease_id,
        success=True,
        now=t0 + timedelta(seconds=12),
    )
    assert complete_lease(
        replacement.lease_id,
        success=True,
        now=t0 + timedelta(seconds=12),
    )


def test_cancellation_stops_new_leases(
    archaeology_manifest: Path,
    raw_store: Path,
) -> None:
    campaign_id, _ = _seed_tasks(
        archaeology_manifest,
        raw_store,
        task_count=4,
        slot_limit=3,
    )
    assert cancel_campaign_tasks(campaign_id=campaign_id, work_ref=WORK_REF) == 4
    assert (
        acquire_next_lease(
            campaign_id=campaign_id,
            work_ref=WORK_REF,
            role="ARCHAEOLOGY_EXTRACTOR",
            backend="deterministic-simulator-v1",
        )
        is None
    )


def test_simulator_is_deterministic() -> None:
    first = run_simulated_task(
        task_id="task-1",
        attempt=1,
        policy_bundle_hash="policy-v1",
    )
    second = run_simulated_task(
        task_id="task-1",
        attempt=1,
        policy_bundle_hash="policy-v1",
    )
    assert first == second
    assert first.status == "SUCCESS"
