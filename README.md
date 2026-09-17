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
