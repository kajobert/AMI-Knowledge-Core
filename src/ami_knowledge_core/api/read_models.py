"""Read models for Encyclopedia UI (search, graph, inspector, reality matrix)."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import HTTPException

from ..db import connect

NodeKind = Literal["batch", "source", "revision", "artifact", "chunk", "claim", "entity"]
InspectKind = Literal["source", "revision", "chunk", "claim", "entity"]


def global_search(q: str, *, limit: int = 15) -> dict[str, Any]:
    pattern = f"%{q}%"
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_id, slug, title, lifecycle_status, implementation_status
            FROM kc_source
            WHERE slug ILIKE %s OR title ILIKE %s OR coalesce(description, '') ILIKE %s
            ORDER BY slug
            LIMIT %s
            """,
            (pattern, pattern, pattern, limit),
        )
        sources = list(cursor.fetchall())

        cursor.execute(
            """
            SELECT claim_id, claim_text, validation_status, lifecycle_status, subject
            FROM kc_claim
            WHERE claim_text ILIKE %s OR subject ILIKE %s OR object_value ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (pattern, pattern, pattern, limit),
        )
        claims = list(cursor.fetchall())

        cursor.execute(
            """
            SELECT entity_id, name, entity_type, lifecycle_status
            FROM kc_entity
            WHERE name ILIKE %s OR coalesce(summary, '') ILIKE %s
            ORDER BY name
            LIMIT %s
            """,
            (pattern, pattern, limit),
        )
        entities = list(cursor.fetchall())

        cursor.execute(
            """
            SELECT chunk_id, revision_id, left(text_content, 240) AS excerpt, ordinal
            FROM kc_chunk
            WHERE text_content ILIKE %s
            ORDER BY ordinal
            LIMIT %s
            """,
            (pattern, limit),
        )
        chunks = list(cursor.fetchall())

    return {
        "query": q,
        "sources": sources,
        "claims": claims,
        "entities": entities,
        "chunks": chunks,
    }


def _matrix_status(
    *,
    lifecycle_status: str,
    implementation_status: str,
    has_conflict: bool,
) -> str:
    if has_conflict:
        return "CONFLICT"
    if lifecycle_status in {"SUPERSEDED", "REJECTED", "DEAD_END"}:
        return lifecycle_status
    if lifecycle_status == "HISTORICAL":
        return "HISTORICAL"
    if lifecycle_status == "CURRENT" and implementation_status in {"IMPLEMENTED", "VALIDATED"}:
        return "CURRENT"
    if lifecycle_status == "CURRENT":
        return "PARTIAL"
    return "UNRESOLVED"


def reality_matrix(*, batch_id: str | None = None) -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.source_id, s.slug, s.title, s.description,
                   s.implementation_status, s.lifecycle_status,
                   r.revision_id, r.content_sha256, r.metadata AS revision_metadata,
                   (
                     SELECT COUNT(*) FROM kc_conflict c
                     WHERE c.status = 'OPEN'
                       AND (
                         c.claim_id_a IN (
                           SELECT claim_id FROM kc_claim_evidence WHERE source_id = s.source_id
                         )
                         OR c.claim_id_b IN (
                           SELECT claim_id FROM kc_claim_evidence WHERE source_id = s.source_id
                         )
                       )
                   ) AS open_conflicts
            FROM kc_source s
            LEFT JOIN LATERAL (
              SELECT revision_id, content_sha256, metadata
              FROM kc_source_revision
              WHERE source_id = s.source_id
              ORDER BY revision_number DESC
              LIMIT 1
            ) r ON TRUE
            ORDER BY s.slug
            """
        )
        rows = list(cursor.fetchall())

    matrix: list[dict[str, Any]] = []
    for row in rows:
        revision_metadata = row.get("revision_metadata") or {}
        if isinstance(revision_metadata, str):
            revision_metadata = json.loads(revision_metadata)
        provenance_batch = (revision_metadata.get("provenance") or {}).get("batch")
        if batch_id:
            meta_batch = revision_metadata.get("batch_id")
            if meta_batch != batch_id and provenance_batch != batch_id:
                continue

        has_conflict = int(row.get("open_conflicts") or 0) > 0
        lifecycle = str(row["lifecycle_status"])
        implementation = str(row["implementation_status"])
        matrix_status = _matrix_status(
            lifecycle_status=lifecycle,
            implementation_status=implementation,
            has_conflict=has_conflict,
        )
        matrix.append(
            {
                "source_id": row["source_id"],
                "slug": row["slug"],
                "title": row["title"],
                "historical_design": row["title"],
                "current_implementation": implementation,
                "lifecycle_status": lifecycle,
                "matrix_status": matrix_status,
                "revision_id": row.get("revision_id"),
                "content_sha256": row.get("content_sha256"),
                "supporting_evidence": _supporting_evidence(row["source_id"]),
            }
        )
    return matrix


def _supporting_evidence(source_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.chunk_id, c.revision_id, c.ordinal,
                   left(c.text_content, 200) AS excerpt,
                   cl.claim_id, cl.claim_text
            FROM kc_chunk c
            LEFT JOIN kc_claim_evidence e ON e.chunk_id = c.chunk_id
            LEFT JOIN kc_claim cl ON cl.claim_id = e.claim_id
            JOIN kc_artifact a ON a.artifact_id = c.artifact_id
            WHERE a.source_id = %s
            ORDER BY c.ordinal
            LIMIT %s
            """,
            (source_id, limit),
        )
        return list(cursor.fetchall())


def lazy_graph(
    *,
    root: str = "batch:archaeology_batch_001",
    depth: int = 1,
    focus: str | None = None,
) -> dict[str, Any]:
    """Return nodes/edges for semantic-zoom graph (lazy expansion)."""

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    zoom = 0

    if focus:
        root = focus

    if root.startswith("batch:"):
        batch_id = root.split(":", 1)[1]
        zoom = 0
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT source_id, slug, title, lifecycle_status
                FROM kc_source
                ORDER BY slug
                """
            )
            for row in cursor.fetchall():
                nodes.append(
                    {
                        "id": f"source:{row['source_id']}",
                        "kind": "source",
                        "label": row["slug"],
                        "title": row["title"],
                        "lifecycle_status": row["lifecycle_status"],
                        "expandable": True,
                    }
                )
                edges.append(
                    {
                        "from": f"batch:{batch_id}",
                        "to": f"source:{row['source_id']}",
                        "kind": "contains",
                    }
                )
        batch_node = {
            "id": f"batch:{batch_id}",
            "kind": "batch",
            "label": batch_id,
            "title": "Archaeology batch",
            "expandable": True,
        }
        nodes.insert(0, batch_node)
        if depth < 1:
            return {"root": root, "zoom": zoom, "nodes": [batch_node], "edges": []}

    if root.startswith("source:"):
        source_id = root.split(":", 1)[1]
        zoom = 1
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_id, slug, title FROM kc_source WHERE source_id = %s",
                (source_id,),
            )
            source = cursor.fetchone()
            if source is None:
                raise HTTPException(status_code=404, detail="source not found")
            nodes.append(
                {
                    "id": f"source:{source_id}",
                    "kind": "source",
                    "label": source["slug"],
                    "title": source["title"],
                    "expandable": True,
                }
            )
            if depth >= 1:
                cursor.execute(
                    """
                    SELECT revision_id, revision_number, content_sha256
                    FROM kc_source_revision
                    WHERE source_id = %s
                    ORDER BY revision_number DESC
                    """,
                    (source_id,),
                )
                for rev in cursor.fetchall():
                    rid = rev["revision_id"]
                    nodes.append(
                        {
                            "id": f"revision:{rid}",
                            "kind": "revision",
                            "label": f"rev-{rev['revision_number']}",
                            "title": rev["content_sha256"][:12],
                            "expandable": True,
                        }
                    )
                    edges.append(
                        {
                            "from": f"source:{source_id}",
                            "to": f"revision:{rid}",
                            "kind": "has_revision",
                        }
                    )
            if depth >= 2:
                cursor.execute(
                    """
                    SELECT c.chunk_id, c.ordinal, c.revision_id
                    FROM kc_chunk c
                    JOIN kc_artifact a ON a.artifact_id = c.artifact_id
                    WHERE a.source_id = %s
                    ORDER BY c.ordinal
                    LIMIT 40
                    """,
                    (source_id,),
                )
                for chunk in cursor.fetchall():
                    cid = chunk["chunk_id"]
                    nodes.append(
                        {
                            "id": f"chunk:{cid}",
                            "kind": "chunk",
                            "label": f"chunk-{chunk['ordinal']}",
                            "title": cid,
                            "expandable": True,
                        }
                    )
                    edges.append(
                        {
                            "from": f"revision:{chunk['revision_id']}",
                            "to": f"chunk:{cid}",
                            "kind": "has_chunk",
                        }
                    )

    if root.startswith("chunk:"):
        chunk_id = root.split(":", 1)[1]
        zoom = 2
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.chunk_id, c.revision_id, c.text_content, a.source_id
                FROM kc_chunk c
                JOIN kc_artifact a ON a.artifact_id = c.artifact_id
                WHERE c.chunk_id = %s
                """,
                (chunk_id,),
            )
            chunk = cursor.fetchone()
            if chunk is None:
                raise HTTPException(status_code=404, detail="chunk not found")
            nodes.append(
                {
                    "id": f"chunk:{chunk_id}",
                    "kind": "chunk",
                    "label": chunk_id[:16],
                    "title": "Evidence chunk",
                    "expandable": False,
                }
            )
            cursor.execute(
                """
                SELECT claim_id, claim_text
                FROM kc_claim cl
                JOIN kc_claim_evidence e ON e.claim_id = cl.claim_id
                WHERE e.chunk_id = %s
                """,
                (chunk_id,),
            )
            for claim in cursor.fetchall():
                nodes.append(
                    {
                        "id": f"claim:{claim['claim_id']}",
                        "kind": "claim",
                        "label": "claim",
                        "title": claim["claim_text"][:80],
                        "expandable": True,
                    }
                )
                edges.append(
                    {
                        "from": f"claim:{claim['claim_id']}",
                        "to": f"chunk:{chunk_id}",
                        "kind": "supported_by",
                    }
                )

    return {"root": root, "zoom": zoom, "nodes": nodes, "edges": edges}


def inspect(kind: InspectKind, object_id: str) -> dict[str, Any]:
    chain: list[dict[str, str]] = []
    payload: dict[str, Any]

    if kind == "source":
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kc_source WHERE source_id = %s", (object_id,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="source not found")
            payload = dict(row)
            chain.append({"kind": "source", "id": object_id, "label": row["slug"]})

    elif kind == "revision":
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.*, s.slug, s.source_id
                FROM kc_source_revision r
                JOIN kc_source s ON s.source_id = r.source_id
                WHERE r.revision_id = %s
                """,
                (object_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="revision not found")
            payload = dict(row)
            chain.extend(
                [
                    {"kind": "source", "id": row["source_id"], "label": row["slug"]},
                    {
                        "kind": "revision",
                        "id": object_id,
                        "label": row.get("revision_label") or object_id,
                    },
                ]
            )

    elif kind == "chunk":
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.*, a.source_id, s.slug, r.revision_number
                FROM kc_chunk c
                JOIN kc_artifact a ON a.artifact_id = c.artifact_id
                JOIN kc_source s ON s.source_id = a.source_id
                JOIN kc_source_revision r ON r.revision_id = c.revision_id
                WHERE c.chunk_id = %s
                """,
                (object_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="chunk not found")
            payload = dict(row)
            chain.extend(
                [
                    {"kind": "source", "id": row["source_id"], "label": row["slug"]},
                    {
                        "kind": "revision",
                        "id": row["revision_id"],
                        "label": f"rev-{row['revision_number']}",
                    },
                    {"kind": "chunk", "id": object_id, "label": f"chunk-{row['ordinal']}"},
                ]
            )

    elif kind == "claim":
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kc_claim WHERE claim_id = %s", (object_id,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="claim not found")
            payload = dict(row)
            chain.append({"kind": "claim", "id": object_id, "label": row["claim_text"][:48]})
            cursor.execute(
                """
                SELECT e.chunk_id, e.source_id, e.revision_id, s.slug
                FROM kc_claim_evidence e
                JOIN kc_source s ON s.source_id = e.source_id
                WHERE e.claim_id = %s
                LIMIT 1
                """,
                (object_id,),
            )
            ev = cursor.fetchone()
            if ev:
                chain.extend(
                    [
                        {"kind": "chunk", "id": ev["chunk_id"], "label": "evidence chunk"},
                        {"kind": "revision", "id": ev["revision_id"], "label": "source revision"},
                        {"kind": "source", "id": ev["source_id"], "label": ev["slug"]},
                    ]
                )

    elif kind == "entity":
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM kc_entity WHERE entity_id = %s", (object_id,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="entity not found")
            payload = dict(row)
            chain.append({"kind": "entity", "id": object_id, "label": row["name"]})
    else:
        raise HTTPException(status_code=400, detail="unsupported inspect kind")

    return {"kind": kind, "id": object_id, "chain": chain, "record": payload}

