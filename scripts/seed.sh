#!/usr/bin/env bash
# Seed IRIS: FHIR resources + MEDDI.* SQL tables (app.fhir.seed), then Vector Search chunks (app.agent.vectors).
# Usage: scripts/seed.sh [--datasets dev,rozsirena] [--reset] [--no-sql]
set -euo pipefail
cd "$(dirname "$0")/../backend"
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
export PYTHONPATH=. PYTHONIOENCODING=utf-8
"$PY" -m app.fhir.seed "$@"
"$PY" -m app.agent.vectors --build
