# CI root cause (PR #6 / PR #7)

## Observation

GitHub Actions runs for PR #6 and PR #7 fail in ~4 seconds with **zero executed steps** (`steps=[]`) for both jobs (`quality`, `postgres-smoke`).

Local validation on the same commits:

- `ruff` OK
- `mypy` OK
- `pytest` OK (including PostgreSQL integration tests)

## Classification

| Layer | Verdict |
|-------|---------|
| GitHub Actions platform / entitlement / startup | **Likely root cause** |
| Workflow YAML on PR branches | Present and syntactically valid |
| Application tests | **Not evidenced as failing** |

## Evidence

- Repository diagnostics (`docs/CI_DIAGNOSTICS.md`) document prior `startup_failure` / zero-job behavior when the repo was private; issue persisted after visibility change.
- Recent run IDs (example): `35444618530`, `35442582331` — jobs created, no steps materialized, immediate failure.
- This pattern predates PR #6 application code and matches GitHub-side job creation failure, not pytest/ruff failures.

## Recommended actions (no test weakening)

1. Inspect run logs/annotations in GitHub UI for `startup_failure` / policy / billing messages.
2. Confirm Actions enabled for `kajobert/AMI-Knowledge-Core` and PR workflows allowed.
3. Merge a minimal workflow fix to `main` only after review (if org requires workflows on default branch).
4. Keep local + postgres integration tests as source of truth until Actions executes steps.

Do **not** disable or weaken tests to simulate green CI.

