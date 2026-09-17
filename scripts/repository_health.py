#!/usr/bin/env python3
"""Fail-closed structural health check for AMI Knowledge Core CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ami_knowledge_core.simulation import report_dict, simulate_repository_loop

REQUIRED_PATHS = (
    Path("README.md"),
    Path("pyproject.toml"),
    Path("src/ami_knowledge_core/contracts.py"),
    Path("src/ami_knowledge_core/identity.py"),
    Path("src/ami_knowledge_core/chunking.py"),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    missing = [str(path) for path in REQUIRED_PATHS if not path.exists()]
    documents: dict[str, str] = {}
    for path in REQUIRED_PATHS:
        if path.exists() and path.suffix in {".md", ".py", ".toml"}:
            documents[str(path)] = path.read_text(encoding="utf-8")

    report = simulate_repository_loop(documents)
    payload = {
        "missing_required_paths": missing,
        "simulation": report_dict(report),
        "strict": args.strict,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if missing:
        return 2
    if not report.passed:
        return 3
    if args.strict and report.source_count != len(REQUIRED_PATHS):
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
