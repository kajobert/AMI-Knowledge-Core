#!/usr/bin/env bash
set -euo pipefail

TS_SERVE_PATH="${KC_TAILSCALE_SERVE_PATH:-/ami-encyclopedia}"
KC_PORT="${KC_BIND_PORT:-8765}"

echo "Stopping preview systemd unit only..."
if systemctl list-unit-files | rg -q ami-kc-encyclopedia-preview; then
  sudo systemctl disable --now ami-kc-encyclopedia-preview.service || true
fi

echo "Removing only Tailscale path route (not full serve reset)..."
if command -v tailscale >/dev/null; then
  sudo tailscale serve --remove-path="$TS_SERVE_PATH" 2>/dev/null || true
  tailscale serve status 2>/dev/null || true
fi

echo "Preview postgres volume left intact (ami_kc_preview_pgdata) for inspection."
echo "Loopback ${KC_PORT} should be closed when service stops."
