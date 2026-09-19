"""Acquisition manifest schema (host-authoritative metadata only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import AccessClass, ImplementationStatus, LifecycleStatus
from ..identity import sha256_text


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    slug: str
    title: str
    file: str
    parser: str
    media_type: str
    description: str | None
    implementation_status: ImplementationStatus
    lifecycle_status: LifecycleStatus
    access_class: AccessClass
    provenance: dict[str, Any]
    origin: str | None


@dataclass(frozen=True, slots=True)
class AcquisitionManifest:
    manifest_version: str
    batch_id: str
    base_dir: Path
    entries: tuple[ManifestEntry, ...]
    raw_json: str
    manifest_sha256: str


def _parse_status(
    value: str,
    enum_cls: type[ImplementationStatus | LifecycleStatus | AccessClass],
) -> Any:
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ValueError(f"invalid status value: {value}") from exc


def load_manifest(manifest_path: Path) -> AcquisitionManifest:
    raw = manifest_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    base_dir = manifest_path.parent
    entries: list[ManifestEntry] = []
    for item in payload.get("entries", []):
        entries.append(
            ManifestEntry(
                slug=str(item["slug"]),
                title=str(item["title"]),
                file=str(item["file"]),
                parser=str(item.get("parser", "markdown")),
                media_type=str(item.get("media_type", "text/markdown")),
                description=item.get("description"),
                implementation_status=_parse_status(
                    str(item.get("implementation_status", "UNKNOWN")),
                    ImplementationStatus,
                ),
                lifecycle_status=_parse_status(
                    str(item.get("lifecycle_status", "UNRESOLVED")),
                    LifecycleStatus,
                ),
                access_class=_parse_status(
                    str(item.get("access_class", "INTERNAL")),
                    AccessClass,
                ),
                provenance=dict(item.get("provenance", {})),
                origin=item.get("origin"),
            )
        )
    return AcquisitionManifest(
        manifest_version=str(payload.get("manifest_version", "1")),
        batch_id=str(payload.get("batch_id", "unknown")),
        base_dir=base_dir,
        entries=tuple(entries),
        raw_json=raw,
        manifest_sha256=sha256_text(raw),
    )

