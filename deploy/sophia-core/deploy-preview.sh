#!/usr/bin/env bash
# Isolated AMI Encyclopedia preview deploy (loopback + optional Tailscale path route).
set -euo pipefail

BRANCH="${KC_PREVIEW_BRANCH:-cursor/archaeology-worker-v01-a2d9}"
REPO_DIR="${KC_PREVIEW_REPO_DIR:-$HOME/AMI-Knowledge-Core}"
ENV_FILE="${KC_PREVIEW_ENV_FILE:-/etc/ami-kc-encyclopedia-preview.env}"
COMPOSE_PROJECT="${KC_PREVIEW_COMPOSE_PROJECT:-ami_kc_preview}"
DB_NAME="${KC_PREVIEW_DB_NAME:-ami_knowledge_core_preview}"
KC_PORT="${KC_BIND_PORT:-8765}"
TS_SERVE_PATH="${KC_TAILSCALE_SERVE_PATH:-/ami-encyclopedia}"

if [[ $EUID -ne 0 ]]; then
  echo "Run deploy with sudo for systemd/env file (or set KC_PREVIEW_SKIP_SYSTEMD=1 for user-mode)."
fi

mkdir -p "$(dirname "$ENV_FILE")"
mkdir -p "$REPO_DIR"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  git clone https://github.com/kajobert/AMI-Knowledge-Core.git "$REPO_DIR"
fi

git -C "$REPO_DIR" fetch origin "$BRANCH"
git -C "$REPO_DIR" checkout "$BRANCH"
git -C "$REPO_DIR" pull origin "$BRANCH" || true

cd "$REPO_DIR"

python3 -m pip install --user -e ".[dev]" >/dev/null

if [[ ! -f "$ENV_FILE" ]]; then
  DB_PASS="$(openssl rand -hex 16)"
  export KC_PREVIEW_DB_PASSWORD="$DB_PASS"
  cat >"$ENV_FILE" <<EOF
DATABASE_URL=postgresql://ami_kc_preview:${DB_PASS}@127.0.0.1:54329/${DB_NAME}
KC_PREVIEW_DB_PASSWORD=${DB_PASS}
KC_BIND_HOST=127.0.0.1
KC_BIND_PORT=${KC_PORT}
KC_AUTO_MIGRATE=1
EOF
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE (credentials not printed)."
fi

# shellcheck disable=SC1090
set -a && source "$ENV_FILE" && set +a
export KC_PREVIEW_DB_PASSWORD="${KC_PREVIEW_DB_PASSWORD:-}"

# Isolated postgres on loopback 54329 via compose project name
export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT"
docker compose -f docker-compose.preview.yml up -d postgres

python3 scripts/run_migrate.py
python3 scripts/ingest_manifest.py fixtures/archaeology_batch_001.manifest.json --migrate
python3 scripts/run_archaeology_worker.py --migrate --discover
python3 scripts/run_archaeology_worker.py --queue-limit 20 || true

if [[ "${KC_PREVIEW_SKIP_SYSTEMD:-0}" != "1" ]] && command -v systemctl >/dev/null; then
  DEPLOY_USER="${SUDO_USER:-$USER}"
  sed "s|@REPO_DIR@|$REPO_DIR|g; s|@ENV_FILE@|$ENV_FILE|g; s|@DEPLOY_USER@|$DEPLOY_USER|g" \
    deploy/systemd/ami-kc-encyclopedia-preview.service \
    | sudo tee /etc/systemd/system/ami-kc-encyclopedia-preview.service >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now ami-kc-encyclopedia-preview.service
else
  echo "KC_PREVIEW_SKIP_SYSTEMD=1 — start manually: source $ENV_FILE && python3 -m ami_knowledge_core.api.server"
fi

echo "=== Local health ==="
curl -sf "http://127.0.0.1:${KC_PORT}/health" | head -c 200
echo

if command -v tailscale >/dev/null; then
  echo "=== Tailscale serve (non-destructive path) ==="
  EXISTING="$(tailscale serve status 2>/dev/null || true)"
  echo "$EXISTING"
  if echo "$EXISTING" | rg -q "Funnel"; then
    echo "ERROR: Funnel detected — aborting tailscale changes"
    exit 1
  fi
  # Path-based route preserves root HTTPS mapping if present.
  sudo tailscale serve --bg --set-path="$TS_SERVE_PATH" "http://127.0.0.1:${KC_PORT}" || {
    echo "tailscale serve path failed — report BLOCKED for tailscale publication"
    exit 2
  }
  tailscale serve status 2>/dev/null || true
fi

echo "Deploy complete."
