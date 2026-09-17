"""Deterministic kernel-like repository simulation used by CI health checks.

This is intentionally non-agentic: it exercises observe -> plan -> validate -> report
without network access, secrets, or write side effects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .chunking import chunk_markdown
from .identity import stable_id


@dataclass(frozen=True, slots=True)
class SimulationReport:
    simulation_id: str
    source_count: int
    chunk_count: int
    duplicate_chunk_ids: int
    passed: bool


def simulate_repository_loop(documents: dict[str, str]) -> SimulationReport:
    """Run a deterministic, side-effect-free approximation of a future kernel loop."""

    chunk_ids: list[str] = []
    for source_name in sorted(documents):
        source_id = stable_id("source", source_name)
        revision_id = stable_id("revision", source_id, documents[source_name])
        artifact_id = stable_id("artifact", source_id, revision_id, source_name)
        chunks = chunk_markdown(revision_id, artifact_id, documents[source_name])
        chunk_ids.extend(chunk.chunk_id for chunk in chunks)

    duplicates = len(chunk_ids) - len(set(chunk_ids))
    simulation_id = stable_id(
        "simulation",
        sorted(documents),
        len(chunk_ids),
        duplicates,
    )
    return SimulationReport(
        simulation_id=simulation_id,
        source_count=len(documents),
        chunk_count=len(chunk_ids),
        duplicate_chunk_ids=duplicates,
        passed=duplicates == 0,
    )


def report_dict(report: SimulationReport) -> dict[str, object]:
    """Return a stable JSON-friendly report payload."""

    return asdict(report)
