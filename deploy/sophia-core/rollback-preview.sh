#!/usr/bin/env bash
set -euo pipefail

TS_SERVE_PATH="${KC_TAILSCALE_SERVE_PATH:-/ami-encyclopedia}"
TS_HTTPS_PORT="${KC_TAILSCALE_HTTPS_PORT:-8443}"
KC_PORT="${KC_BIND_PORT:-8765}"

echo "Stopping preview systemd unit only..."
if systemctl list-unit-files | rg -q ami-kc-encyclopedia-preview; then
  sudo systemctl disable --now ami-kc-encyclopedia-preview.service || true
fi

echo "Removing only the preview Tailscale Serve port/path (not full serve reset)..."
if command -v tailscale >/dev/null; then
  sudo tailscale serve --https="$TS_HTTPS_PORT" off 2>/dev/null || true
  tailscale serve status 2>/dev/null || true
fi

echo "Preview postgres volume left intact (ami_kc_preview_pgdata) for inspection."
echo "Loopback ${KC_PORT} should be closed when service stops."
echo "Preview HTTPS port ${TS_HTTPS_PORT} should be removed; other Serve routes remain untouched."
