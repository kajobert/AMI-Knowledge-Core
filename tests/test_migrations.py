from __future__ import annotations

import psycopg


def test_migrations_clean_install(database_url: str) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'kc_%'
                ORDER BY table_name
                """
        )
        names = [row[0] for row in cursor.fetchall()]
    assert "kc_source" in names
    assert "kc_chunk" in names
    assert "kc_canonical_record" in names
    assert "kc_archaeology_campaign" in names
    assert "kc_archaeology_shard" in names
    assert "kc_archaeology_task" in names
    assert "kc_archaeology_lease" in names

