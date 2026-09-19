# AMI Encyclopedia on sophia-core (private Tailscale path)

This slice is **not** production-deployed. Use the steps below after explicit review.

## Target path

```text
Robert browser → Tailscale → sophia-core → AMI Knowledge Core (loopback) → Encyclopedia dashboard
```

Knowledge Core runs as a **separate AMI service** (not OpenClaw identity/runtime).

## Discover host facts on sophia-core (do not invent hostnames)

```bash
hostname -s
tailscale status --self
tailscale ip -4
```

Use the reported machine name (for example the value from `tailscale status --self`) as `<TS_NAME>` below.

## Recommended service layout

| Component | Bind | Notes |
|-----------|------|-------|
| PostgreSQL + pgvector | `127.0.0.1:5432` (or existing AMI DB host) | Dev compose uses `54329` locally |
| Knowledge Core API/dashboard | `127.0.0.1:8765` | `KC_BIND_HOST=127.0.0.1` |
| Tailscale Serve | HTTPS on tailnet | Proxy to loopback API |

## Example Tailscale Serve (after review)

```bash
export DATABASE_URL='postgresql://ami_kc:***@127.0.0.1:5432/ami_knowledge_core'
export KC_BIND_HOST=127.0.0.1
export KC_BIND_PORT=8765
export KC_AUTO_MIGRATE=1

python scripts/run_migrate.py
ami-kc-serve

# separate shell on sophia-core
tailscale serve --bg --https=443 http://127.0.0.1:8765
tailscale serve status
```

Robert opens the HTTPS URL printed by `tailscale serve status` (MagicDNS form: `https://<TS_NAME>.<tailnet>.ts.net/`).

## Security constraints preserved

- No public ingress / firewall holes for port 8765.
- Do not attach Encyclopedia to OpenClaw Gateway exposure.
- Private raw archives remain outside Git; ingest from host filesystem paths only.

## Rollback

```bash
tailscale serve reset
systemctl stop ami-knowledge-core.service  # if unit was added after review
# database rollback = restore PG snapshot; schema migrations are forward-only in v0
```

