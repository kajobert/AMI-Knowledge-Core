from ami_knowledge_core.simulation import simulate_repository_loop


def test_repository_simulation_is_deterministic_and_clean() -> None:
    documents = {
        "a.md": "# A\nalpha",
        "b.md": "# B\nbeta",
    }
    first = simulate_repository_loop(documents)
    second = simulate_repository_loop(dict(reversed(list(documents.items()))))
    assert first == second
    assert first.source_count == 2
    assert first.chunk_count == 2
    assert first.duplicate_chunk_ids == 0
    assert first.passed is True
