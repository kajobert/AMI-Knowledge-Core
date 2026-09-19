# Issue #10 — sophia-core private Encyclopedia preview

Branch: `cursor/archaeology-worker-v01-a2d9`

## Verified deployment pattern

The real `sophia-core` host uses:
- loopback Knowledge Core: `127.0.0.1:8765`
- isolated preview PostgreSQL: `127.0.0.1:54329`
- Python venv: `.venv` (required on PEP 668 hosts)
- dedicated private Tailscale HTTPS port: `8443`
- path: `/ami-encyclopedia`

Using 8443 intentionally avoids modifying the existing OpenClaw Gateway Serve owner on HTTPS 443.

## On sophia-core

```bash
git clone https://github.com/kajobert/AMI-Knowledge-Core.git ~/AMI-Knowledge-Core
cd ~/AMI-Knowledge-Core
git fetch origin cursor/archaeology-worker-v01-a2d9
git checkout cursor/archaeology-worker-v01-a2d9

bash deploy/sophia-core/preflight.sh | tee /tmp/kc-preflight.txt
sudo bash deploy/sophia-core/deploy-preview.sh
bash deploy/sophia-core/verify-preview.sh
tailscale serve status
```

Expected loopback: `http://127.0.0.1:8765/`

Current verified tailnet route:

`https://sophia-core.tail6f4ebc.ts.net:8443/ami-encyclopedia`

## Rollback (non-destructive)

```bash
sudo bash ~/AMI-Knowledge-Core/deploy/sophia-core/rollback-preview.sh
```

Does **not** run `tailscale serve reset` and does not touch the existing 443 route.

## Isolation

- DB volume: `ami_kc_preview_pgdata`
- DB name: `ami_knowledge_core_preview`
- Env file: `/etc/ami-kc-encyclopedia-preview.env` (600, host-local)
- Service: `ami-kc-encyclopedia-preview.service`
- Preview Tailscale HTTPS port: `8443`
