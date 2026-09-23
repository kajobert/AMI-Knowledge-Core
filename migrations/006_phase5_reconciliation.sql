-- Adaptive Archaeology Phase 5: temporal reconciliation and synthesis.
-- All records are review-only candidates subordinate to the canonical work_ref.
-- Nothing in this migration can promote a canonical record.

CREATE TABLE IF NOT EXISTS kc_reconciliation_run (
  reconciliation_run_id TEXT PRIMARY KEY,
  work_ref TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  input_fingerprint CHAR(64) NOT NULL,
  status TEXT NOT NULL DEFAULT 'RUNNING' CHECK (
    status IN ('RUNNING', 'COMPLETED', 'FAILED')
  ),
  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT,
  UNIQUE (campaign_id, engine_version, policy_version, input_fingerprint)
);

CREATE TABLE IF NOT EXISTS kc_reconciliation_observation (
  observation_id TEXT PRIMARY KEY,
  reconciliation_run_id TEXT NOT NULL
    REFERENCES kc_reconciliation_run (reconciliation_run_id) ON DELETE RESTRICT,
  evidence_id TEXT NOT NULL
    REFERENCES kc_candidate_evidence (evidence_id) ON DELETE RESTRICT,
  reconciliation_key TEXT NOT NULL,
  asserted_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  observed_at TIMESTAMPTZ,
  projection_version TEXT NOT NULL,
  observation_hash CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (valid_from IS NULL AND valid_to IS NULL)
    OR
    (valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_to >= valid_from)
  ),
  UNIQUE (reconciliation_run_id, evidence_id, reconciliation_key)
);

CREATE INDEX IF NOT EXISTS idx_kc_reconciliation_observation_key
  ON kc_reconciliation_observation (reconciliation_run_id, reconciliation_key);

CREATE TABLE IF NOT EXISTS kc_reconciliation_cluster (
  cluster_id TEXT PRIMARY KEY,
  reconciliation_run_id TEXT NOT NULL
    REFERENCES kc_reconciliation_run (reconciliation_run_id) ON DELETE RESTRICT,
  reconciliation_key TEXT NOT NULL,
  normalized_value TEXT NOT NULL,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  observed_at TIMESTAMPTZ,
  member_observation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  member_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (
    reconciliation_run_id,
    reconciliation_key,
    normalized_value,
    valid_from,
    valid_to,
    observed_at
  )
);

CREATE TABLE IF NOT EXISTS kc_contradiction_candidate (
  contradiction_id TEXT PRIMARY KEY,
  reconciliation_run_id TEXT NOT NULL
    REFERENCES kc_reconciliation_run (reconciliation_run_id) ON DELETE RESTRICT,
  reconciliation_key TEXT NOT NULL,
  left_cluster_id TEXT NOT NULL
    REFERENCES kc_reconciliation_cluster (cluster_id) ON DELETE RESTRICT,
  right_cluster_id TEXT NOT NULL
    REFERENCES kc_reconciliation_cluster (cluster_id) ON DELETE RESTRICT,
  classification TEXT NOT NULL CHECK (
    classification IN ('CONTRADICTION', 'UNRESOLVED_TEMPORAL')
  ),
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (
    status IN ('OPEN', 'RESOLVED', 'DISMISSED')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (reconciliation_run_id, left_cluster_id, right_cluster_id)
);

CREATE TABLE IF NOT EXISTS kc_question_candidate (
  question_id TEXT PRIMARY KEY,
  reconciliation_run_id TEXT NOT NULL
    REFERENCES kc_reconciliation_run (reconciliation_run_id) ON DELETE RESTRICT,
  reconciliation_key TEXT NOT NULL,
  question_text TEXT NOT NULL,
  reason TEXT NOT NULL,
  related_cluster_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  related_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (
    status IN ('OPEN', 'ANSWERED', 'DISMISSED')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_synthesis_candidate (
  synthesis_id TEXT PRIMARY KEY,
  reconciliation_run_id TEXT NOT NULL UNIQUE
    REFERENCES kc_reconciliation_run (reconciliation_run_id) ON DELETE RESTRICT,
  work_ref TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  body JSONB NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (
    review_status IN ('DRAFT', 'REVIEWED', 'WITHDRAWN')
  ),
  canonicalization_allowed BOOLEAN NOT NULL DEFAULT FALSE
    CHECK (canonicalization_allowed = FALSE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_kc_question_candidate_open
  ON kc_question_candidate (reconciliation_run_id, status, reconciliation_key);
