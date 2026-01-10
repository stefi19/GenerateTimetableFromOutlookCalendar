#!/bin/bash
set -e

echo "Starting entrypoint..."

# Always run setup for now (debugging)
echo "Running database setup..."

# Initialize DB
python -c "
import sys
sys.path.insert(0, '/app')
from app import init_db, migrate_from_files
init_db()
migrate_from_files()
print('DB initialized')
"

# Populate calendars from CSV
echo "Populating calendars from CSV..."
cd /app && python tools/populate_calendars_from_csv.py

# Update with emails, names, buildings
echo "Updating calendars with CSV data..."
cd /app && python tools/enforce_csv_full_update.py

echo "Setup complete"

# Start the application
exec "$@"