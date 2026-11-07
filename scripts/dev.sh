#!/usr/bin/env bash
# Run every service locally without Docker (SQLite + HTTP event delivery).
# Usage: ./scripts/dev.sh        then open http://localhost:5173
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Secrets such as CAIMEX_API_KEY live in the git-ignored .env at the repo root.
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
export EVENT_WEBHOOK_URL="http://localhost:8004/internal/events"
export CATALOG_URL="http://localhost:8002"
export MONITOR_INTERVAL_SECONDS="${MONITOR_INTERVAL_SECONDS:-120}"

pids=()
trap 'kill "${pids[@]}" 2>/dev/null' EXIT INT TERM
port=8001
for svc in identity catalog orders notifications agent; do
  (cd "$ROOT/services/$svc" && uv sync -q && uv run uvicorn app.main:app --port "$port" --reload --log-level warning) &
  pids+=($!)
  port=$((port + 1))
done
(cd "$ROOT/frontend" && npm install --silent && npm run dev) &
pids+=($!)
wait
