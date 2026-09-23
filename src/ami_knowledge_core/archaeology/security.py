"""Deterministic Phase 1 security policy for archaeology source handling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ..contracts import SensitivityClass


class ExternalizationDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_REDACTED = "ALLOW_REDACTED"
    LOCAL_ONLY = "LOCAL_ONLY"
    DENY = "DENY"


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    name: str
    compressed_size: int
    expanded_size: int
    is_symlink: bool = False
    is_special: bool = False


@dataclass(frozen=True, slots=True)
class ArchivePolicy:
    max_members: int = 10_000
    max_total_expanded_bytes: int = 2_000_000_000
    max_member_expanded_bytes: int = 500_000_000
    max_compression_ratio: float = 200.0


SECRET_VALUE_PATTERNS = (
    re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "execute this command",
    "run this command",
    "tool call",
)


def contains_secret_like_material(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS)


def contains_prompt_injection_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in INJECTION_MARKERS)


def externalization_decision(
    sensitivity: SensitivityClass,
    *,
    backend_allows_private_project: bool = False,
) -> ExternalizationDecision:
    if sensitivity is SensitivityClass.PUBLIC_OR_LOW_SENSITIVITY:
        return ExternalizationDecision.ALLOW
    if sensitivity is SensitivityClass.PRIVATE_PROJECT:
        return (
            ExternalizationDecision.ALLOW
            if backend_allows_private_project
            else ExternalizationDecision.LOCAL_ONLY
        )
    if sensitivity is SensitivityClass.PERSONAL_PRIVATE:
        return ExternalizationDecision.LOCAL_ONLY
    if sensitivity in {
        SensitivityClass.SECRET_LIKE,
        SensitivityClass.CREDENTIAL_CONFIRMED,
        SensitivityClass.UNSAFE_TO_EXTERNALIZE,
    }:
        return ExternalizationDecision.DENY
    return ExternalizationDecision.DENY


def validate_archive_members(
    members: tuple[ArchiveMember, ...],
    *,
    policy: ArchivePolicy | None = None,
) -> None:
    resolved_policy = policy or ArchivePolicy()
    if len(members) > resolved_resolved_policy.max_members:
        raise ValueError("source_archive_member_limit_exceeded")
    total = 0
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("source_archive_path_traversal")
        if member.is_symlink:
            raise ValueError("source_archive_symlink_refused")
        if member.is_special:
            raise ValueError("source_archive_special_file_refused")
        if member.expanded_size < 0 or member.compressed_size < 0:
            raise ValueError("source_archive_size_invalid")
        if member.expanded_size > resolved_policy.max_member_expanded_bytes:
            raise ValueError("source_archive_member_too_large")
        total += member.expanded_size
        if total > resolved_policy.max_total_expanded_bytes:
            raise ValueError("source_archive_expanded_size_limit_exceeded")
        denominator = max(member.compressed_size, 1)
        if member.expanded_size / denominator > resolved_policy.max_compression_ratio:
            raise ValueError("source_archive_compression_ratio_unsafe")
