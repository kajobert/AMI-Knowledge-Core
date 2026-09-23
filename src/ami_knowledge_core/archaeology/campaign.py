"""Subordinate archaeology campaign records bound to canonical AMI work_refs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg

from ..db import connect
from ..identity import canonical_json, stable_id


@dataclass(frozen=True, slots=True)
class CampaignBinding:
    campaign_id: str
    work_ref: str
    corpus_snapshot_id: str
    campaign_version: str
    policy_bundle_hash: str
    slot_limit: int


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def register_corpus_snapshot(
    *,
    revision_refs: Sequence[str],
    source_registry_version: str,
    parser_policy_version: str,
    sensitivity_policy_version: str,
) -> str:
    refs = tuple(sorted({str(ref).strip() for ref in revision_refs if str(ref).strip()}))
    payload = {
        "revision_refs": refs,
        "source_registry_version": source_registry_version,
        "parser_policy_version": parser_policy_version,
        "sensitivity_policy_version": sensitivity_policy_version,
    }
    snapshot_hash = _sha256(payload)
    snapshot_id = stable_id("corpus_snapshot", snapshot_hash)

    with connect() as connection, connection.cursor() as cursor:
        source_ids: set[str] = set()
        if refs:
            cursor.execute(
                """
                SELECT revision_id, source_id
                FROM kc_source_revision
                WHERE revision_id = ANY(%s)
                """,
                (list(refs),),
            )
            rows = cursor.fetchall()
            found = {str(row["revision_id"]) for row in rows}
            missing = sorted(set(refs) - found)
            if missing:
                raise ValueError(f"unknown revision refs: {missing}")
            source_ids = {str(row["source_id"]) for row in rows}

        cursor.execute(
            """
            INSERT INTO kc_corpus_snapshot (
              corpus_snapshot_id, snapshot_hash, revision_refs, source_count, revision_count,
              source_registry_version, parser_policy_version, sensitivity_policy_version
            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_hash) DO NOTHING
            """,
            (
                snapshot_id,
                snapshot_hash,
                json.dumps(list(refs)),
                len(source_ids),
                len(refs),
                source_registry_version,
                parser_policy_version,
                sensitivity_policy_version,
            ),
        )
        cursor.execute(
            "SELECT corpus_snapshot_id FROM kc_corpus_snapshot WHERE snapshot_hash = %s",
            (snapshot_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("corpus snapshot insert/read failed")
        resolved = str(row["corpus_snapshot_id"])
    return resolved


def register_campaign(
    *,
    work_ref: str,
    corpus_snapshot_id: str,
    campaign_version: str,
    policy_bundle_hash: str,
    slot_limit: int = 15,
) -> CampaignBinding:
    work = work_ref.strip()
    if not work.startswith("wr_"):
        raise ValueError("work_ref must be a canonical AMI wr_* reference")
    if not campaign_version.strip():
        raise ValueError("campaign_version required")
    if not policy_bundle_hash.strip():
        raise ValueError("policy_bundle_hash required")
    if not 1 <= slot_limit <= 15:
        raise ValueError("slot_limit must be between 1 and 15")

    campaign_id = stable_id(
        "archaeology_campaign",
        work,
        corpus_snapshot_id,
        campaign_version,
        policy_bundle_hash,
    )
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM kc_corpus_snapshot WHERE corpus_snapshot_id = %s",
            (corpus_snapshot_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError("unknown corpus_snapshot_id")
        cursor.execute(
            """
            INSERT INTO kc_archaeology_campaign (
              campaign_id, work_ref, campaign_version, corpus_snapshot_id,
              policy_bundle_hash, slot_limit, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'CREATED')
            ON CONFLICT (
              work_ref, corpus_snapshot_id, campaign_version, policy_bundle_hash
            ) DO NOTHING
            """,
            (
                campaign_id,
                work,
                campaign_version,
                corpus_snapshot_id,
                policy_bundle_hash,
                slot_limit,
            ),
        )
        cursor.execute(
            """
            SELECT campaign_id, work_ref, corpus_snapshot_id, campaign_version,
                   policy_bundle_hash, slot_limit
            FROM kc_archaeology_campaign
            WHERE work_ref = %s
              AND corpus_snapshot_id = %s
              AND campaign_version = %s
              AND policy_bundle_hash = %s
            """,
            (work, corpus_snapshot_id, campaign_version, policy_bundle_hash),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("campaign insert/read failed")
    return CampaignBinding(
        campaign_id=str(row["campaign_id"]),
        work_ref=str(row["work_ref"]),
        corpus_snapshot_id=str(row["corpus_snapshot_id"]),
        campaign_version=str(row["campaign_version"]),
        policy_bundle_hash=str(row["policy_bundle_hash"]),
        slot_limit=int(row["slot_limit"]),
    )


def require_campaign_binding(
    cursor: psycopg.Cursor[Any],
    *,
    campaign_id: str,
    work_ref: str,
) -> CampaignBinding:
    cursor.execute(
        """
        SELECT campaign_id, work_ref, corpus_snapshot_id, campaign_version,
               policy_bundle_hash, slot_limit
        FROM kc_archaeology_campaign
        WHERE campaign_id = %s
        """,
        (campaign_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("unknown campaign_id")
    if str(row["work_ref"]) != work_ref:
        raise ValueError("campaign_work_ref_mismatch")
    return CampaignBinding(
        campaign_id=str(row["campaign_id"]),
        work_ref=str(row["work_ref"]),
        corpus_snapshot_id=str(row["corpus_snapshot_id"]),
        campaign_version=str(row["campaign_version"]),
        policy_bundle_hash=str(row["policy_bundle_hash"]),
        slot_limit=int(row["slot_limit"]),
    )
