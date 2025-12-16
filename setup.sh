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

echo "Installing Playwright browsers (required for extractor UI rendering)..."
# Install Playwright browser binaries so the extractor and UI rendering work out of the box.
python -m playwright install

echo "Initializing application database and migrating any existing configs..."
# Ensure data directory exists and initialize DB via the app helper functions.
mkdir -p data
"$PY_VENV_DIR/bin/python" -c "from app import init_db, migrate_from_files; init_db(); migrate_from_files(); print('DB initialized')"

echo "Setup complete. Activate with: source $PY_VENV_DIR/bin/activate"
