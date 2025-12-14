#!/usr/bin/env bash
# Helper script to run the Flask app from the project's virtualenv
# Usage: ./run.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtualenv not found at $VENV_DIR"
  echo "Create it with: python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt"
  exit 1
fi

echo "Activating virtualenv: $VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "Ensuring dependencies are installed..."
python -m pip install -r "$ROOT_DIR/requirements.txt"

echo "Starting Flask app (from venv)..."
python "$ROOT_DIR/app.py"
