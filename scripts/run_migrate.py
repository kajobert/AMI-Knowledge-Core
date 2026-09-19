#!/usr/bin/env python3
from __future__ import annotations

from ami_knowledge_core.migrate import apply_migrations


def main() -> int:
    applied = apply_migrations()
    print(f"applied migrations: {applied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

