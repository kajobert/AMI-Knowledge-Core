"""Read-only Knowledge Core HTTP API and Encyclopedia dashboard v0."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..db import connect
from ..migrate import apply_migrations

DASHBOARD_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="AMI Knowledge Core",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.on_event("startup")
def _startup() -> None:
    if os.environ.get("KC_AUTO_MIGRATE", "0") == "1":
        apply_migrations()


@app.get("/health")
def health() -> dict[str, str]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
        cursor.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        row = cursor.fetchone()
    return {
        "status": "ok",
        "pgvector": row["extversion"] if row else "missing",
    }


def _lifecycle_filter(current_only: bool | None) -> tuple[str, list[Any]]:
    if current_only is True:
        return " AND lifecycle_status = 'CURRENT'", []
    if current_only is False:
        return " AND lifecycle_status <> 'CURRENT'", []
    return "", []


@app.get("/api/ingest/runs")
def list_ingest_runs(limit: int = Query(20, ge=1, le=100)) -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT ingest_run_id, manifest_sha256, status, started_at, finished_at, stats
                FROM kc_ingest_run
                ORDER BY started_at DESC
                LIMIT %s
                """,
            (limit,),
        )
        return list(cursor.fetchall())


@app.get("/api/sources")
def list_sources(current: bool | None = Query(None)) -> list[dict[str, Any]]:
    clause, params = _lifecycle_filter(current)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
                SELECT source_id, slug, title, description,
                       implementation_status, lifecycle_status, access_class,
                       created_at, updated_at
                FROM kc_source
                WHERE 1=1{clause}
                ORDER BY slug
                """,
            params,
        )
        return list(cursor.fetchall())


@app.get("/api/sources/{source_id}")
def get_source(source_id: str) -> dict[str, Any]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM kc_source WHERE source_id = %s", (source_id,))
        source = cursor.fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail="source not found")
        cursor.execute(
            """
                SELECT revision_id, revision_number, content_sha256, origin,
                       acquired_at, metadata, created_at
                FROM kc_source_revision
                WHERE source_id = %s
                ORDER BY revision_number DESC
                """,
            (source_id,),
        )
        revisions = list(cursor.fetchall())
        cursor.execute(
            """
                SELECT acquisition_id, content_sha256, ingest_run_id, provenance, acquired_at
                FROM kc_acquisition
                WHERE source_id = %s
                ORDER BY acquired_at DESC
                """,
            (source_id,),
        )
        acquisitions = list(cursor.fetchall())
        cursor.execute(
            """
                SELECT c.claim_id, c.claim_text, c.validation_status
                FROM kc_claim c
                JOIN kc_claim_evidence e ON e.claim_id = c.claim_id
                WHERE e.source_id = %s
                GROUP BY c.claim_id
                ORDER BY c.created_at DESC
                LIMIT 50
                """,
            (source_id,),
        )
        claims = list(cursor.fetchall())
    return {
        "source": source,
        "revisions": revisions,
        "acquisitions": acquisitions,
        "claims": claims,
    }


@app.get("/api/sources/{source_id}/revisions")
def list_revisions(source_id: str) -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT revision_id, revision_number, content_sha256, origin,
                       acquired_at, metadata, created_at
                FROM kc_source_revision
                WHERE source_id = %s
                ORDER BY revision_number DESC
                """,
            (source_id,),
        )
        rows = list(cursor.fetchall())
    if not rows:
        raise HTTPException(status_code=404, detail="source or revisions not found")
    return rows


@app.get("/api/chunks/search")
def search_chunks(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, artifact_id, revision_id, ordinal,
                       left(text_content, 400) AS excerpt,
                       ts_rank(
                         to_tsvector('english', text_content),
                         plainto_tsquery('english', %s)
                       ) AS rank
                FROM kc_chunk
                WHERE to_tsvector('english', text_content) @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
                """,
                (q, q, limit),
            )
            return list(cursor.fetchall())


@app.get("/api/chunks/{chunk_id}")
def get_chunk(chunk_id: str) -> dict[str, Any]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM kc_chunk WHERE chunk_id = %s", (chunk_id,))
        chunk = cursor.fetchone()
        if chunk is None:
            raise HTTPException(status_code=404, detail="chunk not found")
    return dict(chunk)


@app.get("/api/entities")
def list_entities(current: bool | None = Query(None)) -> list[dict[str, Any]]:
    clause, params = _lifecycle_filter(current)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
                SELECT entity_id, entity_type, name, summary,
                       implementation_status, lifecycle_status, created_at
                FROM kc_entity
                WHERE 1=1{clause}
                ORDER BY name
                """,
            params,
        )
        return list(cursor.fetchall())


@app.get("/api/claims")
def list_claims(current: bool | None = Query(None)) -> list[dict[str, Any]]:
    clause, params = _lifecycle_filter(current)
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
                SELECT claim_id, entity_id, subject, predicate, object_value,
                       claim_text, validation_status, lifecycle_status, created_at
                FROM kc_claim
                WHERE 1=1{clause}
                ORDER BY created_at DESC
                LIMIT 200
                """,
            params,
        )
        return list(cursor.fetchall())


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str) -> dict[str, Any]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM kc_claim WHERE claim_id = %s", (claim_id,))
        claim = cursor.fetchone()
        if claim is None:
            raise HTTPException(status_code=404, detail="claim not found")
        cursor.execute(
            """
                SELECT e.claim_id, e.chunk_id, e.source_id, e.revision_id, e.artifact_id,
                       e.relation, c.text_content, s.slug AS source_slug, s.title AS source_title
                FROM kc_claim_evidence e
                JOIN kc_chunk c ON c.chunk_id = e.chunk_id
                JOIN kc_source s ON s.source_id = e.source_id
                WHERE e.claim_id = %s
                """,
            (claim_id,),
        )
        evidence = list(cursor.fetchall())
    return {"claim": claim, "evidence": evidence}


@app.get("/api/conflicts")
def list_conflicts() -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT conflict_id, claim_id_a, claim_id_b, description, status, created_at
                FROM kc_conflict
                ORDER BY created_at DESC
                """
        )
        return list(cursor.fetchall())


@app.get("/api/timeline")
def list_timeline(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT event_id, event_type, source_id, claim_id, ingest_run_id,
                       summary, payload, occurred_at
                FROM kc_timeline_event
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
            (limit,),
        )
        return list(cursor.fetchall())


@app.get("/")
def dashboard_index() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

