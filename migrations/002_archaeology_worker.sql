-- Continuous archaeology worker v0.1

CREATE TABLE IF NOT EXISTS kc_worker_run (
  worker_run_id TEXT PRIMARY KEY,
  worker_kind TEXT NOT NULL DEFAULT 'archaeology_v01',
  status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
  queue_limit INT NOT NULL DEFAULT 50 CHECK (queue_limit > 0),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS kc_archaeology_job (
  job_id TEXT PRIMARY KEY,
  worker_run_id TEXT REFERENCES kc_worker_run (worker_run_id) ON DELETE SET NULL,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  state TEXT NOT NULL CHECK (
    state IN (
      'DISCOVERED',
      'ACQUIRED',
      'PARSED',
      'EXTRACTION_PENDING',
      'EXTRACTED',
      'SYNTHESIS_PENDING',
      'REVIEW_PENDING',
      'ERROR',
      'RETRY_PENDING'
    )
  ),
  processing_fingerprint TEXT NOT NULL,
  attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  last_error TEXT,
  checkpoint JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (revision_id, processing_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_job_state ON kc_archaeology_job (state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_kc_archaeology_job_source ON kc_archaeology_job (source_id);

CREATE TABLE IF NOT EXISTS kc_derived_record (
  derived_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES kc_archaeology_job (job_id) ON DELETE RESTRICT,
  derived_kind TEXT NOT NULL CHECK (
    derived_kind IN ('entity', 'claim', 'relationship', 'decision', 'synthesis_proposal')
  ),
  record_key TEXT NOT NULL,
  processing_fingerprint TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (derived_kind, record_key, processing_fingerprint)
);

CREATE TABLE IF NOT EXISTS kc_synthesis_proposal (
  proposal_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES kc_archaeology_job (job_id) ON DELETE RESTRICT,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  classification TEXT NOT NULL CHECK (
    classification IN (
      'CURRENT',
      'HISTORICAL',
      'SUPERSEDED',
      'PARTIAL',
      'CONFLICT',
      'UNRESOLVED',
      'REUSABLE_IDEA',
      'NO_ACTION'
    )
  ),
  summary TEXT NOT NULL,
  confidence REAL,
  supporting_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  opposing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  review_status TEXT NOT NULL DEFAULT 'REVIEW_PENDING' CHECK (
    review_status IN ('REVIEW_PENDING', 'ACCEPTED', 'REJECTED')
  ),
  processing_fingerprint TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

