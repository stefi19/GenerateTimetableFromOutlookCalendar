#!/usr/bin/env bash
# Small helper to create the project's virtualenv and install dependencies.
# Usage: ./setup.sh
set -euo pipefail

PY_VENV_DIR=".venv"

if [ ! -d "$PY_VENV_DIR" ]; then
  echo "Creating virtualenv in $PY_VENV_DIR..."
  python3 -m venv "$PY_VENV_DIR"
fi

echo "Activating virtualenv and installing requirements..."
# shellcheck disable=SC1091
source "$PY_VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Optionally install Playwright browsers (required for extractor UI rendering):"
echo "  python -m playwright install"

echo "Setup complete. Activate with: source $PY_VENV_DIR/bin/activate"
