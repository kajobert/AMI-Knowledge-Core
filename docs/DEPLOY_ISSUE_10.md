# Issue #10 — sophia-core private Encyclopedia preview

Branch: `cursor/archaeology-worker-v01-a2d9`

## On sophia-core (Robert or private worker agent)

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

Expected tailnet path (if path route succeeds): `https://<sophia-core-tailnet-name>/ami-encyclopedia`

## Rollback (non-destructive)

```bash
sudo bash deploy/sophia-core/rollback-preview.sh
```

Does **not** run `tailscale serve reset`.

## Isolation

- DB volume: `ami_kc_preview_pgdata`
- DB name: `ami_knowledge_core_preview`
- Env file: `/etc/ami-kc-encyclopedia-preview.env` (600, host-local)
- Service: `ami-kc-encyclopedia-preview.service`
