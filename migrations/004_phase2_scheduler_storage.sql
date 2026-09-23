-- Adaptive Archaeology Phase 2 deterministic scheduler storage.
-- Knowledge Core owns durable subordinate records only.
-- AMI Control Plane / Amica remains the scheduler authority.

CREATE UNIQUE INDEX IF NOT EXISTS idx_kc_archaeology_campaign_binding
  ON kc_archaeology_campaign (campaign_id, work_ref);

CREATE TABLE IF NOT EXISTS kc_archaeology_shard (
  shard_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  source_span JSONB NOT NULL,
  chunk_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  partitioner_version TEXT NOT NULL,
  shard_hash CHAR(64) NOT NULL,
  estimated_size INT NOT NULL DEFAULT 0 CHECK (estimated_size >= 0),
  eligible_domain_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT,
  UNIQUE (campaign_id, shard_hash)
);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_shard_revision
  ON kc_archaeology_shard (campaign_id, revision_id, created_at);

CREATE TABLE IF NOT EXISTS kc_archaeology_coverage (
  coverage_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  shard_id TEXT NOT NULL REFERENCES kc_archaeology_shard (shard_id) ON DELETE RESTRICT,
  domain_lens TEXT NOT NULL CHECK (
    domain_lens IN (
      'SOPHIA_IDENTITY',
      'AMICA_AUTONOMY',
      'SYSTEM_ARCHITECTURE',
      'MEMORY_KNOWLEDGE',
      'TRUST_GOVERNANCE_SECURITY',
      'ENTITIES_ROLES',
      'MODEL_ROUTING_INTELLIGENCE',
      'SELF_IMPROVEMENT_EVALS',
      'PRODUCTS_ECOSYSTEM_STRATEGY',
      'CONTRADICTIONS_ABANDONED_IDEAS'
    )
  ),
  analysis_pass TEXT NOT NULL DEFAULT 'DOMAIN_EXTRACTION',
  status TEXT NOT NULL DEFAULT 'UNSEEN' CHECK (
    status IN (
      'UNSEEN',
      'SCHEDULED',
      'IN_PROGRESS',
      'COVERED',
      'NEEDS_REVIEW',
      'BLOCKED',
      'NOT_RELEVANT'
    )
  ),
  coverage_version TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT,
  UNIQUE (campaign_id, shard_id, domain_lens, analysis_pass)
);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_coverage_status
  ON kc_archaeology_coverage (campaign_id, status, domain_lens);

CREATE TABLE IF NOT EXISTS kc_archaeology_task (
  task_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  task_identity_hash CHAR(64) NOT NULL,
  task_kind TEXT NOT NULL,
  role TEXT NOT NULL,
  target_shard_id TEXT REFERENCES kc_archaeology_shard (shard_id) ON DELETE RESTRICT,
  target_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
  domain_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  input_contract_version TEXT NOT NULL,
  output_contract_version TEXT NOT NULL,
  privacy_class TEXT NOT NULL,
  required_capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
  priority_inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
  dependency_task_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  policy_bundle_hash TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING' CHECK (
    state IN (
      'PENDING',
      'LEASED',
      'RUNNING',
      'RESULT_SUBMITTED',
      'VALIDATING',
      'VERIFICATION_PENDING',
      'VERIFIED',
      'RECONCILIATION_PENDING',
      'DONE',
      'RETRY_PENDING',
      'BLOCKED',
      'FAILED',
      'CANCELLED'
    )
  ),
  attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts INT NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  cancelled_at TIMESTAMPTZ,
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT,
  UNIQUE (campaign_id, task_identity_hash)
);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_task_schedulable
  ON kc_archaeology_task (campaign_id, state, updated_at, task_id);

CREATE TABLE IF NOT EXISTS kc_archaeology_lease (
  lease_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  task_id TEXT NOT NULL REFERENCES kc_archaeology_task (task_id) ON DELETE RESTRICT,
  slot_id INT NOT NULL CHECK (slot_id BETWEEN 1 AND 15),
  role TEXT NOT NULL,
  backend TEXT NOT NULL,
  worker_instance_ref TEXT,
  state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (
    state IN ('ACTIVE', 'RELEASED', 'EXPIRED', 'COMPLETED', 'CANCELLED')
  ),
  leased_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  attempt INT NOT NULL CHECK (attempt >= 1),
  policy_bundle_hash TEXT NOT NULL,
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kc_archaeology_active_task_lease
  ON kc_archaeology_lease (task_id)
  WHERE state = 'ACTIVE';

CREATE UNIQUE INDEX IF NOT EXISTS idx_kc_archaeology_active_slot
  ON kc_archaeology_lease (campaign_id, slot_id)
  WHERE state = 'ACTIVE';

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_lease_expiry
  ON kc_archaeology_lease (campaign_id, state, expires_at);

CREATE TABLE IF NOT EXISTS kc_archaeology_run (
  run_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  work_ref TEXT NOT NULL,
  task_id TEXT NOT NULL REFERENCES kc_archaeology_task (task_id) ON DELETE RESTRICT,
  lease_id TEXT NOT NULL REFERENCES kc_archaeology_lease (lease_id) ON DELETE RESTRICT,
  backend TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN ('RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')
  ),
  input_fingerprint CHAR(64) NOT NULL,
  output_hash CHAR(64),
  structured_output JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  FOREIGN KEY (campaign_id, work_ref)
    REFERENCES kc_archaeology_campaign (campaign_id, work_ref)
    ON DELETE RESTRICT,
  UNIQUE (campaign_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_kc_archaeology_run_task
  ON kc_archaeology_run (task_id, started_at DESC);
