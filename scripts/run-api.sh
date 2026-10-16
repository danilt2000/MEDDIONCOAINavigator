#!/usr/bin/env bash
# Start the API on :8100. Env: DEMO_NOW (default 2026-09-09T21:50+02:00), DEMO_DATASET (dev|rozsirena),
# DEMO_REPLAY=0 to skip the history replay, DEMO_WRITE_FHIR=1 to also write the replayed history to IRIS FHIR.
set -euo pipefail
cd "$(dirname "$0")/../backend"
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
PYTHONPATH=. PYTHONIOENCODING=utf-8 exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8100}" "$@"
