# AMI Knowledge Core

AMI Knowledge Core is the provenance-first knowledge layer for the AMI ecosystem.

Canonical design lives in `kajobert/AMI-alpha` under `docs/KNOWLEDGE_CORE_ARCHITECTURE.md`.

Core principles:

- RAW / EVIDENCE is immutable.
- KNOWLEDGE is derived and fully traceable to evidence.
- CANONICAL is review-gated; no model can promote itself automatically.
- implementation status and historical lifecycle are separate axes.
- ingestion is deterministic and idempotent.
- PostgreSQL is authoritative storage; pgvector is optional until an embedding strategy is explicitly chosen.

This repository is intentionally bootstrapped through pull requests and CI.

The default branch contains only the minimal bootstrap required to let GitHub Actions validate feature branches; implementation work lands through pull requests.

## Vertical slice v0 (dev)

```bash
docker compose up -d
export DATABASE_URL=postgresql://ami_kc:ami_kc_dev_password@127.0.0.1:54329/ami_knowledge_core
python -m pip install -e ".[dev]"
python scripts/run_migrate.py
python scripts/healthcheck.py
python scripts/ingest_manifest.py fixtures/archaeology_batch_001.manifest.json --migrate
KC_AUTO_MIGRATE=1 ami-kc-serve
```

Dashboard: `http://127.0.0.1:8765/` · API docs: `http://127.0.0.1:8765/api/docs`

Private deployment pattern for sophia-core: see `docs/DEPLOYMENT_SOPHIA_CORE.md`.
