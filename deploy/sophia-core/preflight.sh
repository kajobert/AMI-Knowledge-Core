#!/usr/bin/env bash
# Read-only preflight for Encyclopedia preview on sophia-core (issue #10).
set -euo pipefail

echo "=== HOSTNAME ==="
hostname -s || hostname
hostname -f 2>/dev/null || true

echo "=== TAILSCALE ==="
if command -v tailscale >/dev/null; then
  tailscale version 2>/dev/null || true
  tailscale status --self 2>/dev/null || tailscale status 2>/dev/null | head -20 || true
  echo "--- tailscale serve status ---"
  tailscale serve status 2>/dev/null || true
else
  echo "tailscale CLI not found"
fi

echo "=== LISTENERS (5432/54329/8765) ==="
if command -v ss >/dev/null; then
  ss -ltnp 2>/dev/null | rg ':(5432|54329|8765)\b' || true
elif command -v netstat >/dev/null; then
  netstat -ltnp 2>/dev/null | rg ':(5432|54329|8765)\b' || true
fi

echo "=== DOCKER/PODMAN ==="
systemctl is-active docker 2>/dev/null || true
systemctl is-active podman 2>/dev/null || true

echo "=== POSTGRESQL ==="
systemctl is-active postgresql 2>/dev/null || true

echo "=== OPENCLAW GATEWAY (inspect only) ==="
ss -ltnp 2>/dev/null | rg -i 'openclaw|gateway|18789|8080' || echo "(no obvious gateway listeners matched)"

echo "=== DISK ==="
df -h / /var/lib 2>/dev/null | tail -n +1

echo "=== AMI-Knowledge-Core checkout ==="
for d in "$HOME/AMI-Knowledge-Core" "/opt/ami/AMI-Knowledge-Core" "/workspace/AMI-Knowledge-Core"; do
  if [[ -d "$d/.git" ]]; then
    echo "found: $d"
    git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null || true
    git -C "$d" log -1 --oneline 2>/dev/null || true
  fi
done

echo "=== PREVIEW ENV FILE (presence only) ==="
if [[ -f /etc/ami-kc-encyclopedia-preview.env ]]; then
  echo "/etc/ami-kc-encyclopedia-preview.env exists"
else
  echo "no /etc/ami-kc-encyclopedia-preview.env yet"
fi
