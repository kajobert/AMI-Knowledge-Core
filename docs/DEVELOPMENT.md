# Development workflow

AMI Knowledge Core is developed through short-lived branches and pull requests.

## Required loop

1. Create a focused branch.
2. Make the smallest coherent change.
3. Open a pull request.
4. Let deterministic CI run.
5. Read failed job logs; fix the cause rather than weakening the check.
6. Merge only when required checks are green and the change has been reviewed at the appropriate risk level.

## Local commands

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy src/ami_knowledge_core
python -m pytest
python scripts/repository_health.py --strict
```

`DATABASE_URL` is required only for the PostgreSQL capability check:

```bash
python scripts/postgres_smoke.py
```

## CI roles

- `CI`: runs on pull requests and pushes to `main`; verifies static quality, tests, deterministic health simulation, and PostgreSQL + pgvector capability.
- `Repository Guardian`: runs daily and on demand; repeats the fail-closed observe/validate/report loop and stores a small health artifact.

The scheduled workflow deliberately has read-only repository permissions and no AI/network model credentials.

## Failure policy

A failed check is evidence. Do not silence or skip it to make the pipeline green unless the check itself is demonstrably wrong and the correction is reviewed.

## Future AI worker

The AI integration is intentionally separate from deterministic CI. See `docs/AI_GITHUB_INTEGRATION.md`. The first stage should comment/review only; it must not merge, deploy, or promote knowledge to canonical state.
