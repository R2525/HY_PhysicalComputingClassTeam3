#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi
export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5050}"
if [ -x ".venv/bin/python" ]; then
  .venv/bin/python app.py
else
  python3 app.py
fi
