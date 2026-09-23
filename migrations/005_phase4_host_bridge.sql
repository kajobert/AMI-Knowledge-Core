-- Adaptive Archaeology Phase 4 bounded host-local bridge.
-- No public mutation API is introduced. These fields make execution policy and
-- safe run diagnostics durable under the canonical work_ref/campaign lineage.

ALTER TABLE kc_archaeology_task
  ADD COLUMN IF NOT EXISTS externalization_decision TEXT NOT NULL DEFAULT 'LOCAL_ONLY'
    CHECK (externalization_decision IN ('ALLOW', 'ALLOW_REDACTED', 'LOCAL_ONLY', 'DENY'));

ALTER TABLE kc_archaeology_task
  ADD COLUMN IF NOT EXISTS payload_redacted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE kc_archaeology_task
  ADD COLUMN IF NOT EXISTS backend_payload JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE kc_archaeology_run
  ADD COLUMN IF NOT EXISTS safe_error_code TEXT;
