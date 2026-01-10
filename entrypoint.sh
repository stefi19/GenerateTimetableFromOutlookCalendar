#!/bin/bash
set -e

# Check if database has calendars, if not, populate
CALENDAR_COUNT=$(python -c "
import sqlite3
try:
    conn = sqlite3.connect('/app/data/app.db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM calendars')
    count = cur.fetchone()[0]
    conn.close()
    print(count)
except:
    print(0)
" 2>/dev/null || echo 0)

if [ "$CALENDAR_COUNT" -eq 0 ]; then
    echo "No calendars found, initializing database..."
    
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
else
    echo "Database already has $CALENDAR_COUNT calendars, skipping setup"
fi

# Start the application
exec "$@"