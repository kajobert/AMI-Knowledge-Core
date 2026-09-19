from __future__ import annotations

from .base import ParsedDocument as ParsedDocument
from .base import ParsedMessage as ParsedMessage
from .base import SourceParser as SourceParser
from .markdown import MarkdownParser
from .plain_text import PlainTextParser

PARSERS: dict[str, SourceParser] = {
    MarkdownParser.parser_key: MarkdownParser(),
    PlainTextParser.parser_key: PlainTextParser(),
}


def get_parser(parser_key: str) -> SourceParser:
    parser = PARSERS.get(parser_key)
    if parser is None:
        raise ValueError(f"unknown parser_key: {parser_key}")
    return parser

