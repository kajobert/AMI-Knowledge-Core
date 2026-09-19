#!/usr/bin/env python3
"""Verify CI can reach PostgreSQL and load pgvector without exposing the database."""

from __future__ import annotations

import os

import psycopg


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("pgvector extension was not loaded")
            print(f"pgvector={row[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
