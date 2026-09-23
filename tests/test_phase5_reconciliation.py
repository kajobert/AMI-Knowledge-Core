from __future__ import annotations

from datetime import UTC, datetime

from ami_knowledge_core.archaeology.reconciliation import (
    Observation,
    build_questions,
    classify_cluster_pairs,
    cluster_observations,
    project_evidence,
)


def _obs(
    evidence_id: str,
    value: str,
    *,
    key: str = "explicit::runtime_version::ami",
    start: datetime | None = None,
    end: datetime | None = None,
) -> Observation:
    return Observation(
        evidence_id=evidence_id,
        reconciliation_key=key,
        asserted_value=value,
        normalized_value=value.casefold(),
        source_id=f"source-{evidence_id}",
        valid_from=start,
        valid_to=end,
        observed_at=None,
    )


def test_exact_duplicates_cluster_without_conflict() -> None:
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    t1 = datetime(2026, 9, 30, tzinfo=UTC)
    clusters = cluster_observations(
        (
            _obs("e1", "v1", start=t0, end=t1),
            _obs("e2", "v1", start=t0, end=t1),
        ),
        run_namespace="run-1",
    )
    assert len(clusters) == 1
    assert clusters[0].member_evidence_ids == ("e1", "e2")
    assert classify_cluster_pairs(clusters) == ()


def test_overlapping_explicit_values_create_contradiction() -> None:
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    t1 = datetime(2026, 9, 30, tzinfo=UTC)
    clusters = cluster_observations(
        (
            _obs("e1", "v1", start=t0, end=t1),
            _obs("e2", "v2", start=t0, end=t1),
        ),
        run_namespace="run-2",
    )
    findings = classify_cluster_pairs(clusters)
    assert len(findings) == 1
    assert findings[0]["classification"] == "CONTRADICTION"
    assert findings[0]["reason"] == "different_values_overlap_in_time"


def test_missing_time_creates_question_not_definitive_conflict() -> None:
    clusters = cluster_observations(
        (
            _obs("e1", "v1"),
            _obs("e2", "v2"),
        ),
        run_namespace="run-3",
    )
    findings = classify_cluster_pairs(clusters)
    assert len(findings) == 1
    assert findings[0]["classification"] == "UNRESOLVED_TEMPORAL"

    questions = build_questions(
        findings,
        {cluster.cluster_id: cluster for cluster in clusters},
        run_namespace="run-3",
    )
    assert len(questions) == 1
    assert "missing effective dates" in questions[0]["question_text"]


def test_non_overlapping_temporal_values_are_not_conflict() -> None:
    jan_start = datetime(2026, 1, 1, tzinfo=UTC)
    jan_end = datetime(2026, 1, 31, tzinfo=UTC)
    feb_start = datetime(2026, 2, 1, tzinfo=UTC)
    feb_end = datetime(2026, 2, 28, tzinfo=UTC)
    clusters = cluster_observations(
        (
            _obs("e1", "v1", start=jan_start, end=jan_end),
            _obs("e2", "v2", start=feb_start, end=feb_end),
        ),
        run_namespace="run-4",
    )
    assert classify_cluster_pairs(clusters) == ()


def test_unstructured_prose_is_only_exact_deduped() -> None:
    first = project_evidence(
        {
            "evidence_id": "e1",
            "source_id": "source-a",
            "claim_type": "architecture",
            "claim_text": "Amica operates the tools.",
            "entity_refs": ["amica"],
            "project_refs": [],
            "source_time_context": None,
        }
    )
    second = project_evidence(
        {
            "evidence_id": "e2",
            "source_id": "source-b",
            "claim_type": "architecture",
            "claim_text": "Amica is the operational layer.",
            "entity_refs": ["amica"],
            "project_refs": [],
            "source_time_context": None,
        }
    )
    assert first.reconciliation_key != second.reconciliation_key
    clusters = cluster_observations((first, second), run_namespace="run-5")
    assert len(clusters) == 2
    assert classify_cluster_pairs(clusters) == ()


def test_structured_projection_uses_explicit_key_and_value() -> None:
    projected = project_evidence(
        {
            "evidence_id": "e1",
            "source_id": "source-a",
            "claim_type": "runtime_fact",
            "claim_text": "Narrative wording is not the compared value.",
            "entity_refs": ["control-plane"],
            "project_refs": [],
            "source_time_context": {
                "reconciliation_key": "runtime.version",
                "asserted_value": "0.3.1",
                "valid_from": "2026-09-23T00:00:00Z",
                "valid_to": "2026-09-23T23:59:59Z",
            },
        }
    )
    assert projected.reconciliation_key.startswith("explicit::runtime.version::")
    assert projected.normalized_value == "0.3.1"
    assert projected.valid_from == datetime(2026, 9, 23, tzinfo=UTC)
