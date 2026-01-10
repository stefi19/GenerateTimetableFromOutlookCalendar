#!/bin/bash
set -e

# Run setup if database doesn't exist
if [ ! -f /app/data/app.db ]; then
    echo "Database not found, initializing..."
    
    # Initialize DB
    python -c "
from app import init_db, migrate_from_files
init_db()
migrate_from_files()
print('DB initialized')
"
    
    # Populate calendars from CSV
    echo "Populating calendars from CSV..."
    python tools/populate_calendars_from_csv.py
    
    # Update with emails, names, buildings
    echo "Updating calendars with CSV data..."
    python tools/enforce_csv_full_update.py
    
    echo "Setup complete"
fi

# Start the application
exec "$@"