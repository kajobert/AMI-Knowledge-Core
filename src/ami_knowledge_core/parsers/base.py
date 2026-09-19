"""Parser contracts for future conversation / document / repo ingest."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """Future chat export anchor (ChatGPT/Gemini/Perplexity)."""

    conversation_id: str
    message_id: str
    role: str
    timestamp: str | None
    text: str
    attachments: tuple[str, ...] = ()
    ordinal: int = 0


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    media_type: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: tuple[ParsedMessage, ...] = ()


class SourceParser(ABC):
    """Versioned parser interface; host assigns artifact/revision IDs."""

    parser_key: str
    parser_version: str

    @abstractmethod
    def parse(self, raw_text: str, *, metadata: dict[str, Any] | None = None) -> ParsedDocument:
        raise NotImplementedError

