# AI integration for GitHub CI

**Status:** DESIGN only. No external model is enabled by this document.

## Goal

Allow an AI reviewer or future AMI Kernel worker to participate in the GitHub development loop without becoming a privileged deployment path.

Target loop:

`observe -> retrieve bounded context -> propose -> branch/PR -> deterministic CI -> human/policy review -> merge -> deploy separately`

## Recommended first integration

Use a GitHub Actions `workflow_dispatch` or explicit PR label as the trigger. The workflow should:

1. check out the exact PR commit read-only;
2. collect bounded context (changed files, tests, relevant architecture docs);
3. call an external model through a small adapter, initially OpenRouter;
4. require structured JSON output against a checked schema;
5. post a PR review/comment only;
6. never push code, merge, expose secrets, or deploy in the first version.

## Security boundaries

- Default GitHub token permissions: `contents: read`, `pull-requests: write` only when a comment/review is required.
- API credentials live only in GitHub Actions secrets, never in the repository or artifacts.
- Do not send the entire repository or evidence vault to an external model by default.
- Context selection must honor future Knowledge Core access classes.
- Model output is untrusted input and must be schema-validated.
- No model may mark knowledge CANONICAL by itself.
- No AI workflow may bypass branch protection or required deterministic CI checks.
- Production deployment remains outside this workflow.

## Evolution path

### Stage 1 — AI reviewer
Read diff + selected context, return findings as a PR comment.

### Stage 2 — proposal agent
Open an issue or produce a patch artifact, still no repository write.

### Stage 3 — bounded coding agent
Create/update a dedicated branch through a narrow GitHub App identity. Required CI and review remain mandatory.

### Stage 4 — AMI Kernel integration
The AMI Kernel becomes the context/router layer. It can select evidence locally, choose a model, validate output, and interact with GitHub through narrow capabilities. GitHub remains the auditable source-of-truth loop.

## Cost control

Before any external inference:

- compute changed-file set locally;
- use deterministic parsing and code/knowledge indexes;
- retrieve only relevant chunks;
- cache by commit SHA + task contract + model version;
- enforce input/output token budgets;
- record cost, latency, model and validation result in Observatory-compatible metadata.

This keeps AI as a replaceable tool behind AMI-owned orchestration rather than embedding model identity into the repository lifecycle.
