#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from ami_knowledge_core.ingest import ingest_manifest
from ami_knowledge_core.migrate import apply_migrations


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest local manifest batch")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--raw-store",
        type=Path,
        default=Path(".data/raw"),
        help="Filesystem raw blob store (never commit private archives)",
    )
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    if args.migrate:
        apply_migrations()
    result = ingest_manifest(args.manifest, raw_store=args.raw_store)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

