from __future__ import annotations

from typing import Any

from .base import ParsedDocument, SourceParser


class MarkdownParser(SourceParser):
    parser_key = "markdown"
    parser_version = "1.0.0"

    def parse(self, raw_text: str, *, metadata: dict[str, Any] | None = None) -> ParsedDocument:
        return ParsedDocument(
            media_type="text/markdown",
            text=raw_text,
            metadata=dict(metadata or {}),
        )

