#!/usr/bin/env python3
"""Service healthcheck: DB connectivity, pgvector, schema presence."""

from __future__ import annotations

from ami_knowledge_core.db import connect


def main() -> int:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        if cursor.fetchone() is None:
            raise RuntimeError("pgvector extension missing")
        cursor.execute(
            """
                SELECT COUNT(*) AS count FROM information_schema.tables
                WHERE table_name LIKE 'kc_%'
                """
        )
        count = int(cursor.fetchone()["count"])
        if count < 5:
            raise RuntimeError("knowledge core schema not migrated")
    print("healthcheck=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

