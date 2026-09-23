"""Durable subordinate Phase 2 scheduler records.

Knowledge Core stores state; it does not own scheduling policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import connect
from ..identity import canonical_json, stable_id
from .campaign import require_campaign_binding


@dataclass(frozen=True, slots=True)
class Lease:
    lease_id: str
    campaign_id: str
    work_ref: str
    task_id: str
    slot_id: int
    attempt: int
    expires_at: datetime


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def register_shard(
    *,
    campaign_id: str,
    work_ref: str,
    source_id: str,
    revision_id: str,
    source_span: dict[str, Any],
    chunk_refs: tuple[str, ...],
    partitioner_version: str,
    eligible_domain_tags: tuple[str, ...],
    sensitivity_class: str,
) -> str:
    material = {
        "campaign_id": campaign_id,
        "source_id": source_id,
        "revision_id": revision_id,
        "source_span": source_span,
        "chunk_refs": sorted(chunk_refs),
        "partitioner_version": partitioner_version,
    }
    shard_hash = _hash(material)
    shard_id = stable_id("archaeology_shard", campaign_id, shard_hash)
    with connect() as connection, connection.cursor() as cursor:
        binding = require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
        cursor.execute(
            """
            SELECT revision_refs
            FROM kc_corpus_snapshot
            WHERE corpus_snapshot_id = %s
            """,
            (binding.corpus_snapshot_id,),
        )
        snapshot = cursor.fetchone()
        refs = snapshot["revision_refs"] if snapshot is not None else []
        if isinstance(refs, str):
            refs = json.loads(refs)
        if revision_id not in refs:
            raise ValueError("campaign_snapshot_mismatch")
        cursor.execute(
            """
            INSERT INTO kc_archaeology_shard (
              shard_id, campaign_id, work_ref, source_id, revision_id,
              source_span, chunk_refs, partitioner_version, shard_hash,
              estimated_size, eligible_domain_tags, sensitivity_class
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (campaign_id, shard_hash) DO NOTHING
            """,
            (
                shard_id,
                campaign_id,
                work_ref,
                source_id,
                revision_id,
                json.dumps(source_span),
                json.dumps(list(sorted(chunk_refs))),
                partitioner_version,
                shard_hash,
                0,
                json.dumps(list(sorted(eligible_domain_tags))),
                sensitivity_class,
            ),
        )
        connection.commit()
    return shard_id


def register_task(
    *,
    campaign_id: str,
    work_ref: str,
    task_kind: str,
    role: str,
    target_shard_id: str | None,
    domain_tags: tuple[str, ...],
    input_contract_version: str,
    output_contract_version: str,
    privacy_class: str,
    required_capabilities: tuple[str, ...],
    policy_bundle_hash: str,
    max_attempts: int = 3,
) -> str:
    if not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts_out_of_range")
    identity = {
        "campaign_id": campaign_id,
        "task_kind": task_kind,
        "role": role,
        "target_shard_id": target_shard_id,
        "domain_tags": sorted(domain_tags),
        "input_contract_version": input_contract_version,
        "output_contract_version": output_contract_version,
        "privacy_class": privacy_class,
        "required_capabilities": sorted(required_capabilities),
        "policy_bundle_hash": policy_bundle_hash,
    }
    task_hash = _hash(identity)
    task_id = stable_id("archaeology_task", campaign_id, task_hash)
    with connect() as connection, connection.cursor() as cursor:
        require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
        cursor.execute(
            """
            INSERT INTO kc_archaeology_task (
              task_id, campaign_id, work_ref, task_identity_hash, task_kind, role,
              target_shard_id, domain_tags, input_contract_version,
              output_contract_version, privacy_class, required_capabilities,
              policy_bundle_hash, max_attempts
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT (campaign_id, task_identity_hash) DO NOTHING
            """,
            (
                task_id,
                campaign_id,
                work_ref,
                task_hash,
                task_kind,
                role,
                target_shard_id,
                json.dumps(list(sorted(domain_tags))),
                input_contract_version,
                output_contract_version,
                privacy_class,
                json.dumps(list(sorted(required_capabilities))),
                policy_bundle_hash,
                max_attempts,
            ),
        )
        connection.commit()
    return task_id


def acquire_next_lease(
    *,
    campaign_id: str,
    work_ref: str,
    role: str,
    backend: str,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> Lease | None:
    current = now or datetime.now(tz=UTC)
    with connect() as connection:
        with connection.cursor() as cursor:
            binding = require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
            cursor.execute(
                """
                SELECT campaign_id
                FROM kc_archaeology_campaign
                WHERE campaign_id = %s AND work_ref = %s
                FOR UPDATE
                """,
                (campaign_id, work_ref),
            )
            if cursor.fetchone() is None:
                raise ValueError("campaign_work_ref_mismatch")
            if binding.slot_limit > 15:
                raise ValueError("campaign_slot_limit_invalid")
            cursor.execute(
                """
                UPDATE kc_archaeology_lease
                SET state = 'EXPIRED'
                WHERE campaign_id = %s
                  AND state = 'ACTIVE'
                  AND expires_at <= %s
                RETURNING task_id
                """,
                (campaign_id, current),
            )
            expired_task_ids = [str(row["task_id"]) for row in cursor.fetchall()]
            if expired_task_ids:
                cursor.execute(
                    """
                    UPDATE kc_archaeology_task
                    SET state='RETRY_PENDING', updated_at=%s
                    WHERE task_id = ANY(%s)
                      AND state IN ('LEASED', 'RUNNING')
                    """,
                    (current, expired_task_ids),
                )
            cursor.execute(
                """
                SELECT slot_id
                FROM generate_series(1, %s) AS slot_id
                WHERE slot_id NOT IN (
                  SELECT slot_id
                  FROM kc_archaeology_lease
                  WHERE campaign_id = %s AND state = 'ACTIVE'
                )
                ORDER BY slot_id
                LIMIT 1
                """,
                (binding.slot_limit, campaign_id),
            )
            slot = cursor.fetchone()
            if slot is None:
                connection.commit()
                return None

            cursor.execute(
                """
                SELECT task_id, attempt_count, max_attempts, policy_bundle_hash
                FROM kc_archaeology_task
                WHERE campaign_id = %s
                  AND work_ref = %s
                  AND state IN ('PENDING', 'RETRY_PENDING')
                  AND attempt_count < max_attempts
                ORDER BY updated_at ASC, task_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (campaign_id, work_ref),
            )
            task = cursor.fetchone()
            if task is None:
                connection.commit()
                return None
            attempt = int(task["attempt_count"]) + 1
            lease_id = stable_id(
                "archaeology_lease",
                campaign_id,
                task["task_id"],
                attempt,
                current.isoformat(),
            )
            expires = current + timedelta(seconds=lease_seconds)
            cursor.execute(
                """
                INSERT INTO kc_archaeology_lease (
                  lease_id, campaign_id, work_ref, task_id, slot_id, role, backend,
                  state, leased_at, heartbeat_at, expires_at, attempt, policy_bundle_hash
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s)
                """,
                (
                    lease_id,
                    campaign_id,
                    work_ref,
                    task["task_id"],
                    int(slot["slot_id"]),
                    role,
                    backend,
                    current,
                    current,
                    expires,
                    attempt,
                    str(task["policy_bundle_hash"]),
                ),
            )
            cursor.execute(
                """
                UPDATE kc_archaeology_task
                SET state='LEASED', attempt_count=%s, updated_at=%s
                WHERE task_id=%s
                """,
                (attempt, current, task["task_id"]),
            )
        connection.commit()
    return Lease(
        lease_id=lease_id,
        campaign_id=campaign_id,
        work_ref=work_ref,
        task_id=str(task["task_id"]),
        slot_id=int(slot["slot_id"]),
        attempt=attempt,
        expires_at=expires,
    )


def heartbeat_lease(
    lease_id: str,
    *,
    extend_seconds: int = 60,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(tz=UTC)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE kc_archaeology_lease
            SET heartbeat_at=%s, expires_at=%s
            WHERE lease_id=%s
              AND state='ACTIVE'
              AND expires_at > %s
            """,
            (current, current + timedelta(seconds=extend_seconds), lease_id, current),
        )
        changed = cursor.rowcount == 1
        connection.commit()
        return changed


def complete_lease(
    lease_id: str,
    *,
    success: bool,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(tz=UTC)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT task_id, expires_at, state
            FROM kc_archaeology_lease
            WHERE lease_id=%s
            FOR UPDATE
            """,
            (lease_id,),
        )
        row = cursor.fetchone()
        if row is None or row["state"] != "ACTIVE" or row["expires_at"] <= current:
            connection.rollback()
            return False
        cursor.execute(
            "UPDATE kc_archaeology_lease SET state=%s WHERE lease_id=%s",
            ("COMPLETED" if success else "RELEASED", lease_id),
        )
        cursor.execute(
            """
            UPDATE kc_archaeology_task
            SET state=%s, updated_at=%s
            WHERE task_id=%s
            """,
            ("DONE" if success else "RETRY_PENDING", current, row["task_id"]),
        )
        connection.commit()
        return True


def cancel_campaign_tasks(*, campaign_id: str, work_ref: str) -> int:
    with connect() as connection, connection.cursor() as cursor:
        require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
        cursor.execute(
            """
            UPDATE kc_archaeology_task
            SET state='CANCELLED', cancelled_at=now(), updated_at=now()
            WHERE campaign_id=%s
              AND work_ref=%s
              AND state NOT IN ('DONE','FAILED','CANCELLED')
            """,
            (campaign_id, work_ref),
        )
        changed = cursor.rowcount
        cursor.execute(
            """
            UPDATE kc_archaeology_lease
            SET state='CANCELLED'
            WHERE campaign_id=%s AND state='ACTIVE'
            """,
            (campaign_id,),
        )
        connection.commit()
        return changed


def upsert_coverage(
    *,
    campaign_id: str,
    work_ref: str,
    shard_id: str,
    domain_lens: str,
    analysis_pass: str = "DOMAIN_EXTRACTION",
    status: str = "UNSEEN",
    coverage_version: str = "coverage-v1",
) -> str:
    coverage_id = stable_id(
        "archaeology_coverage",
        campaign_id,
        shard_id,
        domain_lens,
        analysis_pass,
    )
    with connect() as connection, connection.cursor() as cursor:
        require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
        cursor.execute(
            """
            INSERT INTO kc_archaeology_coverage (
              coverage_id, campaign_id, work_ref, shard_id, domain_lens,
              analysis_pass, status, coverage_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (campaign_id, shard_id, domain_lens, analysis_pass)
            DO UPDATE SET
              status=EXCLUDED.status,
              coverage_version=EXCLUDED.coverage_version,
              updated_at=now()
            """,
            (
                coverage_id,
                campaign_id,
                work_ref,
                shard_id,
                domain_lens,
                analysis_pass,
                status,
                coverage_version,
            ),
        )
        connection.commit()
    return coverage_id
