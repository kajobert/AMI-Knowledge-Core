"""Deterministic, versioned chunking with provenance anchors."""

from __future__ import annotations

from dataclasses import dataclass

from .identity import sha256_text, stable_id

MARKDOWN_CHUNKER_VERSION = "markdown-v1"
PLAIN_TEXT_CHUNKER_VERSION = "plain_text-v1"


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_id: str
    ordinal: int
    start_line: int
    end_line: int
    text: str
    content_sha256: str
    chunker_version: str
    heading_path: tuple[str, ...] = ()


MarkdownChunk = TextChunk

PLAIN_TEXT_MAX_LINES = 80


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
                chunker_version=MARKDOWN_CHUNKER_VERSION,
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


def chunk_plain_text(revision_id: str, artifact_id: str, text: str) -> list[TextChunk]:
    """Split plain text into fixed-size line windows (deterministic)."""

    if not revision_id.strip() or not artifact_id.strip():
        raise ValueError("revision_id and artifact_id must not be empty")

    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(lines):
        end = min(start + PLAIN_TEXT_MAX_LINES, len(lines))
        body = "\n".join(lines[start:end]).strip()
        if body:
            ordinal = len(chunks)
            content_hash = sha256_text(body)
            chunk_id = stable_id(
                "chunk",
                revision_id,
                artifact_id,
                ordinal,
                content_hash,
                PLAIN_TEXT_CHUNKER_VERSION,
            )
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    ordinal=ordinal,
                    start_line=start + 1,
                    end_line=end,
                    text=body,
                    content_sha256=content_hash,
                    chunker_version=PLAIN_TEXT_CHUNKER_VERSION,
                )
            )
        start = end
    return chunks
