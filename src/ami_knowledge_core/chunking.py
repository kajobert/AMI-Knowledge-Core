"""Deterministic Markdown chunking with provenance anchors."""

from __future__ import annotations

from dataclasses import dataclass

from .identity import sha256_text, stable_id


@dataclass(frozen=True, slots=True)
class MarkdownChunk:
    chunk_id: str
    ordinal: int
    heading_path: tuple[str, ...]
    start_line: int
    end_line: int
    text: str
    content_sha256: str


def chunk_markdown(revision_id: str, artifact_id: str, text: str) -> list[MarkdownChunk]:
    """Split Markdown by headings while preserving deterministic line anchors."""

    if not revision_id.strip() or not artifact_id.strip():
        raise ValueError("revision_id and artifact_id must not be empty")

    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[MarkdownChunk] = []
    heading_stack: list[str] = []
    buffer: list[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal buffer, start_line
        body = "\n".join(buffer).strip()
        if not body:
            buffer = []
            return
        ordinal = len(chunks)
        content_hash = sha256_text(body)
        chunk_id = stable_id(
            "chunk",
            revision_id,
            artifact_id,
            ordinal,
            content_hash,
        )
        chunks.append(
            MarkdownChunk(
                chunk_id=chunk_id,
                ordinal=ordinal,
                heading_path=tuple(heading_stack),
                start_line=start_line,
                end_line=end_line,
                text=body,
                content_sha256=content_hash,
            )
        )
        buffer = []

    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            marker = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[marker:].strip()
            if 1 <= marker <= 6 and title:
                flush(line_number - 1)
                heading_stack[:] = heading_stack[: marker - 1]
                while len(heading_stack) < marker - 1:
                    heading_stack.append("")
                heading_stack.append(title)
                buffer = [line]
                start_line = line_number
                continue

        if not buffer:
            start_line = line_number
        buffer.append(line)

    flush(len(lines))
    return chunks
