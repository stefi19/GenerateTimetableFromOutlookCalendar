#!/bin/bash
set -e

# Raise the soft/hard nofile limit for the current shell so child processes
# inherit a higher file descriptor limit. Docker ulimits sometimes don't
# propagate to all runtimes on macOS/older dockerd setups, so setting here
# provides an additional safety net.
ulimit -n 65536 || true

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

# Populate calendars from CSV (if present)
echo "Populating calendars from CSV..."
# Look for canonical CSV in several locations and run the population script only if found.
CSV_CANDIDATES=("/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv" "/app/Rooms_PUBLISHER_HTML-ICS(in).csv" "/app/playwright_captures/Rooms_PUBLISHER_HTML-ICS(in).csv")
CSV_FOUND=0
for p in "${CSV_CANDIDATES[@]}"; do
	if [ -f "$p" ]; then
		echo "Found CSV at $p - populating calendars"
		cd /app && python tools/populate_calendars_from_csv.py || true
		CSV_FOUND=1
		break
	fi
done
if [ "$CSV_FOUND" -eq 0 ]; then
	echo "Warning: CSV file 'Rooms_PUBLISHER_HTML-ICS(in).csv' not found - skipping population step"
fi

# Update with emails, names, buildings
echo "Updating calendars with CSV data..."
cd /app && python tools/enforce_csv_full_update.py

echo "Setup complete"

# Ensure app files are owned by the non-root runtime user so Playwright and
# the application can access installed browser binaries and caches.
chown -R appuser:appuser /app || true

# Drop privileges to `appuser` when launching the main process so Playwright
# runs with the same user that installed browsers during image build.
# Use `su` to run the provided command as appuser. This preserves the
# existing behavior but ensures the runtime user has the expected home
# directory and cache paths.
exec su -s /bin/bash appuser -c "$*"