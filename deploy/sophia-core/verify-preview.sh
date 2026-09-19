#!/usr/bin/env bash
set -euo pipefail
KC_PORT="${KC_BIND_PORT:-8765}"
BASE="http://127.0.0.1:${KC_PORT}"

check() {
  local path="$1"
  echo -n "$path "
  curl -sf -o /dev/null -w "%{http_code}\n" "${BASE}${path}"
}

check /health
check /api/docs
check /
check /api/sources
check "/api/search?q=Sophia"
check "/api/graph?root=batch:archaeology_batch_001&depth=1"
check /api/reality-matrix
check /api/worker/status
check /api/worker/jobs
