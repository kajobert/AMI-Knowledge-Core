# CI diagnostics

2026-09-17: repository visibility changed from private to public to isolate a GitHub Actions `BuildFailed` / `startup_failure` / zero-jobs condition observed in the private repository.

This commit intentionally makes no runtime or security-policy change. Its purpose is to trigger a fresh public-repository CI run so the private-repository billing/entitlement hypothesis can be tested against the same workflow definition.

Expected diagnostic result:

- if real jobs are created, the private-repository Actions layer was the likely blocker;
- if the run still fails before jobs exist, preserve run IDs and treat the failure as GitHub Actions platform/registry behavior rather than project code.
