"""Deterministic Phase 5 reconciliation over validated candidate evidence.

The engine only creates review-only reconciliation artifacts. It never writes
kc_canonical_record and never marks candidate evidence CANONICAL.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from ..db import connect
from ..identity import canonical_json, stable_id
from .campaign import require_campaign_binding

ENGINE_VERSION = "phase5-reconciliation-v1"
POLICY_VERSION = "phase5-conservative-temporal-v1"
PROJECTION_VERSION = "phase5-projection-v1"


@dataclass(frozen=True, slots=True)
class Observation:
    evidence_id: str
    reconciliation_key: str
    asserted_value: str
    normalized_value: str
    source_id: str
    valid_from: datetime | None
    valid_to: datetime | None
    observed_at: datetime | None


@dataclass(frozen=True, slots=True)
class Cluster:
    cluster_id: str
    reconciliation_key: str
    normalized_value: str
    valid_from: datetime | None
    valid_to: datetime | None
    observed_at: datetime | None
    member_evidence_ids: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    reconciliation_run_id: str
    observation_count: int
    cluster_count: int
    contradiction_count: int
    question_count: int
    synthesis_id: str


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _time_projection(context: dict[str, Any] | None) -> tuple[datetime | None, datetime | None, datetime | None]:
    if not context:
        return None, None, None
    valid_from = _parse_dt(
        context.get("valid_from")
        or context.get("effective_from")
        or context.get("start")
    )
    valid_to = _parse_dt(
        context.get("valid_to")
        or context.get("effective_to")
        or context.get("end")
    )
    observed_at = _parse_dt(
        context.get("observed_at")
        or context.get("asserted_at")
        or context.get("timestamp")
    )
    if valid_from is not None and valid_to is None:
        valid_to = valid_from
    if valid_to is not None and valid_from is None:
        valid_from = valid_to
    return valid_from, valid_to, observed_at


def project_evidence(row: dict[str, Any]) -> Observation:
    claim_type = str(row["claim_type"]).strip()
    entity_refs = row.get("entity_refs") or []
    project_refs = row.get("project_refs") or []
    if isinstance(entity_refs, str):
        entity_refs = json.loads(entity_refs)
    if isinstance(project_refs, str):
        project_refs = json.loads(project_refs)
    subject_refs = sorted(str(item) for item in [*entity_refs, *project_refs] if str(item).strip())
    subject = "|".join(subject_refs) if subject_refs else str(row["source_id"])
    context = row.get("source_time_context")
    if isinstance(context, str):
        context = json.loads(context)
    context = context if isinstance(context, dict) else {}
    explicit_key = str(context.get("reconciliation_key", "")).strip()
    asserted = str(context.get("asserted_value") or row["claim_text"]).strip()
    normalized = _normalize_text(asserted)
    if explicit_key:
        key = f"explicit::{explicit_key.casefold()}::{subject}"
    else:
        # Unstructured prose can be exact-deduplicated, but must never be
        # compared as a contradiction merely because wording differs.
        key = f"text::{claim_type.casefold()}::{subject}::{normalized}"
    valid_from, valid_to, observed_at = _time_projection(context)
    return Observation(
        evidence_id=str(row["evidence_id"]),
        reconciliation_key=key,
        asserted_value=asserted,
        normalized_value=normalized,
        source_id=str(row["source_id"]),
        valid_from=valid_from,
        valid_to=valid_to,
        observed_at=observed_at,
    )


def _cluster_identity(obs: Observation) -> tuple[Any, ...]:
    return (
        obs.reconciliation_key,
        obs.normalized_value,
        obs.valid_from,
        obs.valid_to,
        obs.observed_at,
    )


def cluster_observations(
    observations: Iterable[Observation],
    *,
    run_namespace: str = "pure",
) -> tuple[Cluster, ...]:
    grouped: dict[tuple[Any, ...], list[Observation]] = {}
    for obs in observations:
        grouped.setdefault(_cluster_identity(obs), []).append(obs)

    result: list[Cluster] = []
    for identity, members in sorted(grouped.items(), key=lambda item: repr(item[0])):
        key, normalized_value, valid_from, valid_to, observed_at = identity
        evidence_ids = tuple(sorted({item.evidence_id for item in members}))
        source_ids = tuple(sorted({item.source_id for item in members}))
        cluster_id = stable_id(
            "reconciliation_cluster",
            run_namespace,
            str(key),
            str(normalized_value),
            *(item for item in evidence_ids),
        )
        result.append(
            Cluster(
                cluster_id=cluster_id,
                reconciliation_key=str(key),
                normalized_value=str(normalized_value),
                valid_from=valid_from,
                valid_to=valid_to,
                observed_at=observed_at,
                member_evidence_ids=evidence_ids,
                source_ids=source_ids,
            )
        )
    return tuple(result)


def _intervals_overlap(left: Cluster, right: Cluster) -> bool | None:
    if (
        left.valid_from is None
        or left.valid_to is None
        or right.valid_from is None
        or right.valid_to is None
    ):
        return None
    return left.valid_from <= right.valid_to and right.valid_from <= left.valid_to


def classify_cluster_pairs(clusters: Iterable[Cluster]) -> tuple[dict[str, Any], ...]:
    items = tuple(clusters)
    findings: list[dict[str, Any]] = []
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left.reconciliation_key != right.reconciliation_key:
                continue
            if left.normalized_value == right.normalized_value:
                continue
            overlap = _intervals_overlap(left, right)
            if overlap is True:
                classification = "CONTRADICTION"
                reason = "different_values_overlap_in_time"
            elif overlap is None:
                classification = "UNRESOLVED_TEMPORAL"
                reason = "different_values_missing_complete_time_bounds"
            else:
                continue
            pair = sorted((left.cluster_id, right.cluster_id))
            findings.append(
                {
                    "contradiction_id": stable_id(
                        "contradiction_candidate",
                        left.reconciliation_key,
                        pair[0],
                        pair[1],
                        classification,
                    ),
                    "reconciliation_key": left.reconciliation_key,
                    "left_cluster_id": pair[0],
                    "right_cluster_id": pair[1],
                    "classification": classification,
                    "reason": reason,
                }
            )
    return tuple(findings)


def build_questions(
    findings: Iterable[dict[str, Any]],
    cluster_by_id: dict[str, Cluster],
    *,
    run_namespace: str = "pure",
) -> tuple[dict[str, Any], ...]:
    questions: list[dict[str, Any]] = []
    for finding in findings:
        if finding["classification"] != "UNRESOLVED_TEMPORAL":
            continue
        left = cluster_by_id[finding["left_cluster_id"]]
        right = cluster_by_id[finding["right_cluster_id"]]
        evidence_ids = tuple(sorted({*left.member_evidence_ids, *right.member_evidence_ids}))
        question_text = (
            f"Which value is temporally current for {finding['reconciliation_key']}, "
            "and what are the missing effective dates?"
        )
        questions.append(
            {
                "question_id": stable_id(
                    "question_candidate",
                    run_namespace,
                    finding["reconciliation_key"],
                    *evidence_ids,
                ),
                "reconciliation_key": finding["reconciliation_key"],
                "question_text": question_text,
                "reason": finding["reason"],
                "related_cluster_ids": [left.cluster_id, right.cluster_id],
                "related_evidence_ids": list(evidence_ids),
            }
        )
    return tuple(questions)


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    material = [
        {
            "evidence_id": str(row["evidence_id"]),
            "packet_hash": str(row["packet_hash"]),
            "validation_status": str(row["validation_status"]),
        }
        for row in sorted(rows, key=lambda item: str(item["evidence_id"]))
    ]
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def reconcile_campaign(
    *,
    work_ref: str,
    campaign_id: str,
    engine_version: str = ENGINE_VERSION,
    policy_version: str = POLICY_VERSION,
) -> ReconciliationResult:
    with connect() as connection, connection.cursor() as cursor:
        require_campaign_binding(cursor, campaign_id=campaign_id, work_ref=work_ref)
        cursor.execute(
            """
            SELECT evidence_id, source_id, claim_text, claim_type, entity_refs, project_refs,
                   source_time_context, semantic_hash, packet_hash, validation_status, canonical_status
            FROM kc_candidate_evidence
            WHERE campaign_id=%s AND work_ref=%s AND validation_status='PASS'
              AND canonical_status <> 'REJECTED'
            ORDER BY evidence_id
            """,
            (campaign_id, work_ref),
        )
        rows = [dict(row) for row in cursor.fetchall()]

        input_fingerprint = _fingerprint(rows)
        run_id = stable_id(
            "reconciliation_run",
            campaign_id,
            engine_version,
            policy_version,
            input_fingerprint,
        )
        cursor.execute(
            """
            SELECT reconciliation_run_id, status, summary
            FROM kc_reconciliation_run
            WHERE campaign_id=%s AND engine_version=%s
              AND policy_version=%s AND input_fingerprint=%s
            """,
            (campaign_id, engine_version, policy_version, input_fingerprint),
        )
        existing = cursor.fetchone()
        if existing is not None and str(existing["status"]) == "COMPLETED":
            summary = existing["summary"] or {}
            if isinstance(summary, str):
                summary = json.loads(summary)
            return ReconciliationResult(
                reconciliation_run_id=str(existing["reconciliation_run_id"]),
                observation_count=int(summary.get("observation_count", 0)),
                cluster_count=int(summary.get("cluster_count", 0)),
                contradiction_count=int(summary.get("contradiction_count", 0)),
                question_count=int(summary.get("question_count", 0)),
                synthesis_id=str(summary.get("synthesis_id", "")),
            )

        cursor.execute(
            """
            INSERT INTO kc_reconciliation_run (
              reconciliation_run_id, work_ref, campaign_id, engine_version,
              policy_version, input_fingerprint, status
            ) VALUES (%s,%s,%s,%s,%s,%s,'RUNNING')
            ON CONFLICT (reconciliation_run_id) DO NOTHING
            """,
            (
                run_id,
                work_ref,
                campaign_id,
                engine_version,
                policy_version,
                input_fingerprint,
            ),
        )

        observations = tuple(project_evidence(row) for row in rows)
        observation_id_by_evidence: dict[str, str] = {}
        for obs in observations:
            observation_hash = hashlib.sha256(
                canonical_json(
                    {
                        "evidence_id": obs.evidence_id,
                        "key": obs.reconciliation_key,
                        "value": obs.normalized_value,
                        "valid_from": obs.valid_from.isoformat() if obs.valid_from else None,
                        "valid_to": obs.valid_to.isoformat() if obs.valid_to else None,
                        "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
                    }
                ).encode("utf-8")
            ).hexdigest()
            observation_id = stable_id(
                "reconciliation_observation",
                run_id,
                obs.evidence_id,
                obs.reconciliation_key,
            )
            observation_id_by_evidence[obs.evidence_id] = observation_id
            cursor.execute(
                """
                INSERT INTO kc_reconciliation_observation (
                  observation_id, reconciliation_run_id, evidence_id,
                  reconciliation_key, asserted_value, normalized_value, source_id,
                  valid_from, valid_to, observed_at, projection_version, observation_hash
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (reconciliation_run_id, evidence_id, reconciliation_key)
                DO NOTHING
                """,
                (
                    observation_id,
                    run_id,
                    obs.evidence_id,
                    obs.reconciliation_key,
                    obs.asserted_value,
                    obs.normalized_value,
                    obs.source_id,
                    obs.valid_from,
                    obs.valid_to,
                    obs.observed_at,
                    PROJECTION_VERSION,
                    observation_hash,
                ),
            )

        clusters = cluster_observations(observations, run_namespace=run_id)
        for cluster in clusters:
            member_observation_ids = [
                observation_id_by_evidence[evidence_id]
                for evidence_id in cluster.member_evidence_ids
            ]
            cursor.execute(
                """
                INSERT INTO kc_reconciliation_cluster (
                  cluster_id, reconciliation_run_id, reconciliation_key,
                  normalized_value, valid_from, valid_to, observed_at,
                  member_observation_ids, member_evidence_ids, source_ids
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
                ON CONFLICT (cluster_id) DO NOTHING
                """,
                (
                    cluster.cluster_id,
                    run_id,
                    cluster.reconciliation_key,
                    cluster.normalized_value,
                    cluster.valid_from,
                    cluster.valid_to,
                    cluster.observed_at,
                    json.dumps(member_observation_ids),
                    json.dumps(list(cluster.member_evidence_ids)),
                    json.dumps(list(cluster.source_ids)),
                ),
            )

        cluster_by_id = {cluster.cluster_id: cluster for cluster in clusters}
        findings = classify_cluster_pairs(clusters)
        for finding in findings:
            cursor.execute(
                """
                INSERT INTO kc_contradiction_candidate (
                  contradiction_id, reconciliation_run_id, reconciliation_key,
                  left_cluster_id, right_cluster_id, classification, reason
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (contradiction_id) DO NOTHING
                """,
                (
                    finding["contradiction_id"],
                    run_id,
                    finding["reconciliation_key"],
                    finding["left_cluster_id"],
                    finding["right_cluster_id"],
                    finding["classification"],
                    finding["reason"],
                ),
            )

        questions = build_questions(findings, cluster_by_id, run_namespace=run_id)
        for question in questions:
            cursor.execute(
                """
                INSERT INTO kc_question_candidate (
                  question_id, reconciliation_run_id, reconciliation_key,
                  question_text, reason, related_cluster_ids, related_evidence_ids
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT (question_id) DO NOTHING
                """,
                (
                    question["question_id"],
                    run_id,
                    question["reconciliation_key"],
                    question["question_text"],
                    question["reason"],
                    json.dumps(question["related_cluster_ids"]),
                    json.dumps(question["related_evidence_ids"]),
                ),
            )

        synthesis_id = stable_id("synthesis_candidate", run_id)
        synthesis_body = {
            "engine_version": engine_version,
            "policy_version": policy_version,
            "observation_count": len(observations),
            "cluster_count": len(clusters),
            "contradictions": list(findings),
            "questions": list(questions),
            "canonicalization_allowed": False,
        }
        cursor.execute(
            """
            INSERT INTO kc_synthesis_candidate (
              synthesis_id, reconciliation_run_id, work_ref, campaign_id,
              body, review_status, canonicalization_allowed
            ) VALUES (%s,%s,%s,%s,%s::jsonb,'DRAFT',FALSE)
            ON CONFLICT (reconciliation_run_id)
            DO UPDATE SET body=EXCLUDED.body
            """,
            (
                synthesis_id,
                run_id,
                work_ref,
                campaign_id,
                json.dumps(synthesis_body),
            ),
        )
        summary = {
            "observation_count": len(observations),
            "cluster_count": len(clusters),
            "contradiction_count": sum(
                1 for finding in findings if finding["classification"] == "CONTRADICTION"
            ),
            "question_count": len(questions),
            "synthesis_id": synthesis_id,
        }
        cursor.execute(
            """
            UPDATE kc_reconciliation_run
            SET status='COMPLETED', summary=%s::jsonb, completed_at=now()
            WHERE reconciliation_run_id=%s
            """,
            (json.dumps(summary), run_id),
        )
        connection.commit()

    return ReconciliationResult(
        reconciliation_run_id=run_id,
        observation_count=len(observations),
        cluster_count=len(clusters),
        contradiction_count=summary["contradiction_count"],
        question_count=len(questions),
        synthesis_id=synthesis_id,
    )
