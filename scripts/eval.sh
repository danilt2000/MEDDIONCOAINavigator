#!/usr/bin/env bash
# Replay + metrics against ground truth -> backend/reports/eval_<dataset>.json (served at /api/eval/latest-<dataset>).
# Usage: scripts/eval.sh [dev|rozsirena|all] [--no-llm]
set -euo pipefail
cd "$(dirname "$0")/../backend"
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
dataset="${1:-all}"; shift || true
PYTHONPATH=. PYTHONIOENCODING=utf-8 exec "$PY" -m app.eval --dataset "$dataset" "$@"
