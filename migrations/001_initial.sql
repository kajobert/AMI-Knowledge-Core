-- AMI Knowledge Core — initial schema (dev bootstrap)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kc_schema_migration (
  version INT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_ingest_run (
  ingest_run_id TEXT PRIMARY KEY,
  manifest_sha256 CHAR(64),
  status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS kc_raw_blob (
  content_sha256 CHAR(64) PRIMARY KEY,
  byte_length BIGINT NOT NULL CHECK (byte_length >= 0),
  storage_ref TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_source (
  source_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT,
  implementation_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (
    implementation_status IN (
      'DESIGN', 'RESEARCH', 'EXPERIMENT', 'PoC', 'IMPLEMENTED', 'VALIDATED', 'UNKNOWN'
    )
  ),
  lifecycle_status TEXT NOT NULL DEFAULT 'UNRESOLVED' CHECK (
    lifecycle_status IN (
      'CURRENT', 'SUPERSEDED', 'REJECTED', 'DEAD_END', 'HISTORICAL', 'UNRESOLVED'
    )
  ),
  access_class TEXT NOT NULL DEFAULT 'INTERNAL' CHECK (
    access_class IN ('PUBLIC', 'INTERNAL', 'SENSITIVE', 'RESTRICTED')
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_source_revision (
  revision_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  content_sha256 CHAR(64) NOT NULL REFERENCES kc_raw_blob (content_sha256) ON DELETE RESTRICT,
  revision_number INT NOT NULL CHECK (revision_number >= 1),
  revision_label TEXT,
  origin TEXT,
  acquired_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_id, revision_number),
  UNIQUE (source_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS kc_acquisition (
  acquisition_id TEXT PRIMARY KEY,
  content_sha256 CHAR(64) NOT NULL REFERENCES kc_raw_blob (content_sha256) ON DELETE RESTRICT,
  ingest_run_id TEXT NOT NULL REFERENCES kc_ingest_run (ingest_run_id) ON DELETE RESTRICT,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_acquisition_content ON kc_acquisition (content_sha256);
CREATE INDEX IF NOT EXISTS idx_kc_acquisition_source ON kc_acquisition (source_id);

CREATE TABLE IF NOT EXISTS kc_artifact (
  artifact_id TEXT PRIMARY KEY,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  media_type TEXT NOT NULL,
  relative_path TEXT,
  parser_key TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_chunk (
  chunk_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES kc_artifact (artifact_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  ordinal INT NOT NULL CHECK (ordinal >= 0),
  content_sha256 CHAR(64) NOT NULL,
  chunker_version TEXT NOT NULL,
  text_content TEXT NOT NULL,
  anchor JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(1536),
  UNIQUE (artifact_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_kc_chunk_revision ON kc_chunk (revision_id);
CREATE INDEX IF NOT EXISTS idx_kc_chunk_text_trgm ON kc_chunk USING gin (to_tsvector('english', text_content));

CREATE TABLE IF NOT EXISTS kc_entity (
  entity_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  name TEXT NOT NULL,
  summary TEXT,
  implementation_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (
    implementation_status IN (
      'DESIGN', 'RESEARCH', 'EXPERIMENT', 'PoC', 'IMPLEMENTED', 'VALIDATED', 'UNKNOWN'
    )
  ),
  lifecycle_status TEXT NOT NULL DEFAULT 'CURRENT' CHECK (
    lifecycle_status IN (
      'CURRENT', 'SUPERSEDED', 'REJECTED', 'DEAD_END', 'HISTORICAL', 'UNRESOLVED'
    )
  ),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_entity_alias (
  alias_id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES kc_entity (entity_id) ON DELETE RESTRICT,
  alias TEXT NOT NULL,
  UNIQUE (entity_id, alias)
);

CREATE TABLE IF NOT EXISTS kc_claim (
  claim_id TEXT PRIMARY KEY,
  entity_id TEXT REFERENCES kc_entity (entity_id) ON DELETE SET NULL,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_value TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK (
    validation_status IN ('PROPOSED', 'SUPPORTED', 'VALIDATED', 'REJECTED')
  ),
  implementation_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (
    implementation_status IN (
      'DESIGN', 'RESEARCH', 'EXPERIMENT', 'PoC', 'IMPLEMENTED', 'VALIDATED', 'UNKNOWN'
    )
  ),
  lifecycle_status TEXT NOT NULL DEFAULT 'UNRESOLVED' CHECK (
    lifecycle_status IN (
      'CURRENT', 'SUPERSEDED', 'REJECTED', 'DEAD_END', 'HISTORICAL', 'UNRESOLVED'
    )
  ),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_claim_evidence (
  claim_id TEXT NOT NULL REFERENCES kc_claim (claim_id) ON DELETE RESTRICT,
  chunk_id TEXT NOT NULL REFERENCES kc_chunk (chunk_id) ON DELETE RESTRICT,
  source_id TEXT NOT NULL REFERENCES kc_source (source_id) ON DELETE RESTRICT,
  revision_id TEXT NOT NULL REFERENCES kc_source_revision (revision_id) ON DELETE RESTRICT,
  artifact_id TEXT NOT NULL REFERENCES kc_artifact (artifact_id) ON DELETE RESTRICT,
  relation TEXT NOT NULL DEFAULT 'supports' CHECK (relation IN ('supports', 'opposes')),
  PRIMARY KEY (claim_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS kc_relationship (
  relationship_id TEXT PRIMARY KEY,
  from_entity_id TEXT NOT NULL REFERENCES kc_entity (entity_id) ON DELETE RESTRICT,
  to_entity_id TEXT NOT NULL REFERENCES kc_entity (entity_id) ON DELETE RESTRICT,
  relationship_type TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kc_conflict (
  conflict_id TEXT PRIMARY KEY,
  claim_id_a TEXT NOT NULL REFERENCES kc_claim (claim_id) ON DELETE RESTRICT,
  claim_id_b TEXT NOT NULL REFERENCES kc_claim (claim_id) ON DELETE RESTRICT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'WONT_FIX')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kc_canonical_record (
  canonical_id TEXT PRIMARY KEY,
  record_type TEXT NOT NULL,
  title TEXT NOT NULL,
  body JSONB NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'REVIEWED' CHECK (
    review_status IN ('DRAFT', 'REVIEWED', 'WITHDRAWN')
  ),
  supporting_claim_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  opposing_claim_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  promoted_by TEXT NOT NULL,
  promoted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (promoted_by <> 'llm' AND promoted_by <> 'LLM')
);

CREATE TABLE IF NOT EXISTS kc_timeline_event (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  source_id TEXT REFERENCES kc_source (source_id) ON DELETE SET NULL,
  claim_id TEXT REFERENCES kc_claim (claim_id) ON DELETE SET NULL,
  ingest_run_id TEXT REFERENCES kc_ingest_run (ingest_run_id) ON DELETE SET NULL,
  summary TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_timeline_occurred ON kc_timeline_event (occurred_at DESC);

