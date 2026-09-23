-- Adaptive Archaeology Phase 1 foundation.
-- These records are subordinate to the canonical AMI Control Plane work lifecycle.
-- Legacy archaeology jobs may remain unanchored for audit, but integrated execution
-- must only create and run jobs with both work_ref and campaign_id.

ALTER TABLE kc_source
  ADD COLUMN IF NOT EXISTS sensitivity_class TEXT NOT NULL DEFAULT 'PRIVATE_PROJECT';

ALTER TABLE kc_source
  DROP CONSTRAINT IF EXISTS kc_source_sensitivity_class_check;

ALTER TABLE kc_source
  ADD CONSTRAINT kc_source_sensitivity_class_check CHECK (
    sensitivity_class IN (
      'PUBLIC_OR_LOW_SENSITIVITY',
      'PRIVATE_PROJECT',
      'PERSONAL_PRIVATE',
      'SECRET_LIKE',
      'CREDENTIAL_CONFIRMED',
      'UNSAFE_TO_EXTERNALIZE'
    )
  );

CREATE TABLE IF NOT EXISTS kc_corpus_snapshot (
  corpus_snapshot_id TEXT PRIMARY KEY,
  snapshot_hash CHAR(64) NOT NULL UNIQUE,
  revision_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_count INT NOT NULL DEFAULT 0 CHECK (source_count >= 0),
  revision_count INT NOT NULL DEFAULT 0 CHECK (revision_count >= 0),
  source_registry_version TEXT NOT NULL,
  parser_policy_version TEXT NOT NULL,
  sensitivity_policy_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_archaeology_campaign (
  campaign_id TEXT PRIMARY KEY,
  work_ref TEXT NOT NULL,
  campaign_version TEXT NOT NULL,
  corpus_snapshot_id TEXT NOT NULL
    REFERENCES kc_corpus_snapshot (corpus_snapshot_id) ON DELETE RESTRICT,
  policy_bundle_hash TEXT NOT NULL,
  slot_limit INT NOT NULL CHECK (slot_limit BETWEEN 1 AND 15),
  status TEXT NOT NULL DEFAULT 'CREATED' CHECK (
    status IN (
      'CREATED',
      'INVENTORY',
      'PARTITIONING',
      'ACTIVE',
      'READY_FOR_REVIEW',
      'COMPLETED',
      'BLOCKED',
      'FAILED',
      'CANCELLED'
    )
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  failure_code TEXT,
  UNIQUE (work_ref, corpus_snapshot_id, campaign_version, policy_bundle_hash)
);

ALTER TABLE kc_archaeology_job
  ADD COLUMN IF NOT EXISTS work_ref TEXT;

ALTER TABLE kc_archaeology_job
  ADD COLUMN IF NOT EXISTS campaign_id TEXT
    REFERENCES kc_archaeology_campaign (campaign_id) ON DELETE RESTRICT;

ALTER TABLE kc_archaeology_job
  DROP CONSTRAINT IF EXISTS kc_archaeology_job_anchor_pair_check;

ALTER TABLE kc_archaeology_job
  ADD CONSTRAINT kc_archaeology_job_anchor_pair_check CHECK (
    (work_ref IS NULL AND campaign_id IS NULL)
    OR
    (work_ref IS NOT NULL AND campaign_id IS NOT NULL)
  );

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_job_campaign
  ON kc_archaeology_job (campaign_id, state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_job_work
  ON kc_archaeology_job (work_ref, state, updated_at DESC);

CREATE TABLE IF NOT EXISTS kc_candidate_evidence (
  evidence_id TEXT PRIMARY KEY,
  evidence_schema_version TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  campaign_id TEXT NOT NULL
    REFERENCES kc_archaeology_campaign (campaign_id) ON DELETE RESTRICT,
  task_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  source_hash CHAR(64) NOT NULL,
  source_span JSONB NOT NULL,
  source_chunk_id TEXT REFERENCES kc_chunk (chunk_id) ON DELETE RESTRICT,
  source_time_context JSONB,
  claim_text TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  domain_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  entity_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  project_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_kind TEXT NOT NULL CHECK (
    evidence_kind IN (
      'DIRECT_QUOTE',
      'SOURCE_PARAPHRASE',
      'DERIVED_RELATIONSHIP',
      'MODEL_HYPOTHESIS',
      'QUESTION_CANDIDATE'
    )
  ),
  extractor_role TEXT NOT NULL,
  backend TEXT NOT NULL,
  model TEXT,
  prompt_template_version TEXT,
  model_confidence REAL CHECK (
    model_confidence IS NULL OR (model_confidence >= 0.0 AND model_confidence <= 1.0)
  ),
  historical_status TEXT NOT NULL DEFAULT 'UNRESOLVED' CHECK (
    historical_status IN (
      'CURRENT',
      'SUPERSEDED',
      'REJECTED',
      'DEAD_END',
      'HISTORICAL',
      'UNRESOLVED'
    )
  ),
  canonical_status TEXT NOT NULL DEFAULT 'EVIDENCE_ONLY' CHECK (
    canonical_status IN (
      'EVIDENCE_ONLY',
      'CURRENT_CANDIDATE',
      'CANONICAL',
      'REJECTED'
    )
  ),
  sensitivity_class TEXT NOT NULL CHECK (
    sensitivity_class IN (
      'PUBLIC_OR_LOW_SENSITIVITY',
      'PRIVATE_PROJECT',
      'PERSONAL_PRIVATE',
      'SECRET_LIKE',
      'CREDENTIAL_CONFIRMED',
      'UNSAFE_TO_EXTERNALIZE'
    )
  ),
  validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
    validation_status IN ('PENDING', 'PASS', 'FAIL', 'NOT_RUN')
  ),
  semantic_hash CHAR(64) NOT NULL,
  packet_hash CHAR(64) NOT NULL,
  idempotency_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (campaign_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_kc_candidate_evidence_source
  ON kc_candidate_evidence (source_id, revision_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kc_candidate_evidence_work
  ON kc_candidate_evidence (work_ref, campaign_id, created_at DESC);

CREATE TABLE IF NOT EXISTS kc_evidence_validation (
  validation_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL
    REFERENCES kc_candidate_evidence (evidence_id) ON DELETE RESTRICT,
  validator_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL', 'NOT_RUN')),
  checks JSONB NOT NULL DEFAULT '[]'::jsonb,
  safe_error_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
  validated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_evidence_validation_evidence
  ON kc_evidence_validation (evidence_id, validated_at DESC);
