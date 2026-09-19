from __future__ import annotations

import json
from typing import Any

import psycopg

from ..identity import stable_id
from .contract import SynthesisProposal


def apply_synthesis_proposals(
    cursor: psycopg.Cursor[Any],
    *,
    job_id: str,
    processing_fingerprint: str,
    proposals: tuple[SynthesisProposal, ...],
) -> int:
    written = 0
    for proposal in proposals:
        proposal_id = stable_id("synthesis", processing_fingerprint, proposal.key)
        cursor.execute(
            """
            INSERT INTO kc_derived_record (
              derived_id, job_id, derived_kind, record_key, processing_fingerprint, payload
            ) VALUES (%s, %s, 'synthesis_proposal', %s, %s, %s::jsonb)
            ON CONFLICT (derived_kind, record_key, processing_fingerprint) DO NOTHING
            """,
            (
                stable_id("derived", job_id, "synthesis", proposal.key),
                job_id,
                proposal.key,
                processing_fingerprint,
                json.dumps({"proposal_id": proposal_id}),
            ),
        )
        if cursor.rowcount:
            written += 1
        cursor.execute(
            """
            INSERT INTO kc_synthesis_proposal (
              proposal_id, job_id, source_id, revision_id, classification, summary,
              confidence, supporting_evidence, opposing_evidence,
              review_status, processing_fingerprint, metadata
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
              'REVIEW_PENDING', %s, %s::jsonb
            )
            ON CONFLICT (proposal_id) DO NOTHING
            """,
            (
                proposal_id,
                job_id,
                proposal.source_id,
                proposal.revision_id,
                proposal.classification,
                proposal.summary,
                proposal.confidence,
                json.dumps(list(proposal.supporting_evidence)),
                json.dumps(list(proposal.opposing_evidence)),
                processing_fingerprint,
                json.dumps(proposal.metadata),
            ),
        )
    return written

