from ami_knowledge_core.chunking import chunk_markdown, chunk_plain_text

SAMPLE = """# Title
Intro text.

## Section
Body line one.
Body line two.
"""


def test_chunking_is_deterministic() -> None:
    first = chunk_markdown("rev_1", "artifact_1", SAMPLE)
    second = chunk_markdown("rev_1", "artifact_1", SAMPLE)
    assert first == second
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_chunking_preserves_heading_and_lines() -> None:
    chunks = chunk_markdown("rev_1", "artifact_1", SAMPLE)
    assert len(chunks) == 2
    assert chunks[0].heading_path == ("Title",)
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[1].heading_path == ("Title", "Section")
    assert chunks[1].start_line == 4
    assert chunks[1].end_line == 6


def test_empty_document_has_no_chunks() -> None:
    assert chunk_markdown("rev_1", "artifact_1", "") == []


def test_plain_text_chunk_ids_are_deterministic() -> None:
    text = "\n".join(f"line {index}" for index in range(1, 200))
    first = chunk_plain_text("rev_1", "artifact_1", text)
    second = chunk_plain_text("rev_1", "artifact_1", text)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.chunker_version == "plain_text-v1" for chunk in first)
