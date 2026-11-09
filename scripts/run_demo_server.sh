#!/usr/bin/env bash
# Keep the PreFlight demo server alive inside tmux.
# Ctrl+C stops Uvicorn, then this loop restarts it. Use "make stop" to stop the demo.
set -u
cd "$(dirname "$0")/.."

# Local demo only: a stable key keeps an already-open page's CSRF token valid
# when tmux restarts Uvicorn. Never use this value outside the local demo; the
# application still generates a random per-process fallback when the variable
# is unset (for example in production or tests).
export PREFLIGHT_SECRET_KEY="${PREFLIGHT_SECRET_KEY:-preflight-local-demo-only-not-for-production}"

while true; do
  echo "[preflight] starting uvicorn..."
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  code=$?
  echo "[preflight] server exited with code ${code}; restarting in 2s"
  echo "[preflight] detach with Ctrl+b then d. Stop with: make stop"
  sleep 2
done
