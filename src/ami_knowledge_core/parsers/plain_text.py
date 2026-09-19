from __future__ import annotations

from typing import Any

from .base import ParsedDocument, SourceParser


class PlainTextParser(SourceParser):
    parser_key = "plain_text"
    parser_version = "1.0.0"

    def parse(self, raw_text: str, *, metadata: dict[str, Any] | None = None) -> ParsedDocument:
        return ParsedDocument(
            media_type="text/plain",
            text=raw_text,
            metadata=dict(metadata or {}),
        )

