"""Apply numbered SQL migrations idempotently."""

from __future__ import annotations

from pathlib import Path

from .db import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda path: path.name)


def applied_versions() -> set[int]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'kc_schema_migration'
                """
        )
        if cursor.fetchone() is None:
            return set()
        cursor.execute("SELECT version FROM kc_schema_migration")
        return {int(row["version"]) for row in cursor.fetchall()}


def apply_migrations() -> list[int]:
    applied: list[int] = []
    done = applied_versions()
    for path in migration_files():
        version = int(path.name.split("_", 1)[0])
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO kc_schema_migration (version) VALUES (%s)",
                    (version,),
                )
            connection.commit()
        applied.append(version)
    return applied

