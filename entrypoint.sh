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

# Initialize DB (use a small script rather than a -c/heredoc so __file__ is defined)
if python3 -c "import sys" >/dev/null 2>&1; then
    python3 /app/tools/init_db.py || true
else
    # fallback to whatever python is available
    python /app/tools/init_db.py || true
fi

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

# Update with emails, names, buildings (only if CSV exists)
echo "Updating calendars with CSV data..."
CSV_CHECK_FOUND=0
for p in "${CSV_CANDIDATES[@]}"; do
    if [ -f "$p" ]; then
        echo "Found CSV at $p - running enforce_csv_full_update"
        cd /app && python tools/enforce_csv_full_update.py || true
        CSV_CHECK_FOUND=1
        break
    fi
done
if [ "$CSV_CHECK_FOUND" -eq 0 ]; then
    echo "Warning: CSV file 'Rooms_PUBLISHER_HTML-ICS(in).csv' not found - skipping enforce_csv_full_update"
fi

echo "Setup complete"

# Ensure app files are owned by the non-root runtime user so Playwright and
# the application can access installed browser binaries and caches.
chown -R appuser:appuser /app || true

# Auto-start detached full extraction if not already running and there are enabled calendars
PIDFILE=/app/playwright_captures/extract_detached.pid
echo "Checking for existing detached extractor..."
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Detached extractor already running with PID $PID"
    else
        echo "Stale or empty pidfile found, removing"
        rm -f "$PIDFILE" || true
    fi
fi

# Start extractor if no pidfile and calendars exist (or CSV was found earlier)
if [ ! -f "$PIDFILE" ]; then
    echo "No detached extractor running; checking DB for enabled calendars..."
    # Use a small helper script so Python runs from a file (avoids __file__ issues)
    if python3 -c "import sys" >/dev/null 2>&1; then
        ENABLED_COUNT=$(python3 /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
    else
        ENABLED_COUNT=$(python /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
    fi
    echo "Enabled calendars in DB: ${ENABLED_COUNT}"
    if [ "${ENABLED_COUNT}" -gt 0 ]; then
        echo "Starting detached full extraction as appuser..."
        su -s /bin/bash appuser -c "mkdir -p /app/playwright_captures && nohup python3 /app/tools/run_full_extraction.py > /app/playwright_captures/extract_stdout.txt 2>/app/playwright_captures/extract_stderr.txt & echo \$! > /app/playwright_captures/extract_detached.pid" || true
        echo "Detached extractor started, pidfile: $PIDFILE"
    else
        echo "No enabled calendars found - skipping detached extraction start"
    fi
fi

# Drop privileges to `appuser` when launching the main process so Playwright
# runs with the same user that installed browsers during image build.
# Use `su` to run the provided command as appuser. This preserves the
# existing behavior but ensures the runtime user has the expected home
# directory and cache paths.
exec su -s /bin/bash appuser -c "$*"
#!/bin/bash
set -e

# Raise the soft/hard nofile limit for the current shell so child processes
	echo "No detached extractor running; checking DB for enabled calendars..."
	# Use a small helper script so Python runs from a file (avoids __file__ issues)
	if python3 -c "import sys" >/dev/null 2>&1; then
# inherit a higher file descriptor limit. Docker ulimits sometimes don't
# propagate to all runtimes on macOS/older dockerd setups, so setting here
# provides an additional safety net.
ulimit -n 65536 || true

echo "Starting entrypoint..."

# Always run setup for now (debugging)
echo "Running database setup..."

# Initialize DB (use a small script rather than a -c/heredoc so __file__ is defined)
if python3 -c "import sys" >/dev/null 2>&1; then
	python3 /app/tools/init_db.py || true
else
	# fallback to whatever python is available
	python /app/tools/init_db.py || true
fi

		ENABLED_COUNT=$(python3 /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
	else
		ENABLED_COUNT=$(python /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
	fi
	echo "Enabled calendars in DB: ${ENABLED_COUNT}"
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

# Update with emails, names, buildings (only if CSV exists)
echo "Updating calendars with CSV data..."
CSV_CHECK_FOUND=0
for p in "${CSV_CANDIDATES[@]}"; do
	if [ -f "$p" ]; then
		echo "Found CSV at $p - running enforce_csv_full_update"
		cd /app && python tools/enforce_csv_full_update.py || true
		CSV_CHECK_FOUND=1
		break
	fi
done
if [ "$CSV_CHECK_FOUND" -eq 0 ]; then
	echo "Warning: CSV file 'Rooms_PUBLISHER_HTML-ICS(in).csv' not found - skipping enforce_csv_full_update"
fi

echo "Setup complete"

# Ensure app files are owned by the non-root runtime user so Playwright and
# the application can access installed browser binaries and caches.
chown -R appuser:appuser /app || true

# Auto-start detached full extraction if not already running and there are enabled calendars
PIDFILE=/app/playwright_captures/extract_detached.pid
echo "Checking for existing detached extractor..."
if [ -f "$PIDFILE" ]; then
	PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
	if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
		echo "Detached extractor already running with PID $PID"
	else
		echo "Stale or empty pidfile found, removing"
		rm -f "$PIDFILE" || true
	fi
fi

# Start extractor if no pidfile and calendars exist (or CSV was found earlier)
if [ ! -f "$PIDFILE" ]; then
	echo "No detached extractor running; checking DB for enabled calendars..."
	ENABLED_COUNT=$(python3 - <<'PY'
import sqlite3
import os
db='/app/data/app.db'
if not os.path.exists(db):
	print(0)
else:
	if [ "${ENABLED_COUNT}" -gt 0 ]; then
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

	# Initialize DB (use a small script rather than a -c/heredoc so __file__ is defined)
	if python3 -c "import sys" >/dev/null 2>&1; then
		python3 /app/tools/init_db.py || true
	else
		# fallback to whatever python is available
		python /app/tools/init_db.py || true
	fi

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

	# Update with emails, names, buildings (only if CSV exists)
	echo "Updating calendars with CSV data..."
	CSV_CHECK_FOUND=0
	for p in "${CSV_CANDIDATES[@]}"; do
		if [ -f "$p" ]; then
			echo "Found CSV at $p - running enforce_csv_full_update"
			cd /app && python tools/enforce_csv_full_update.py || true
			CSV_CHECK_FOUND=1
			break
		fi
	done
	if [ "$CSV_CHECK_FOUND" -eq 0 ]; then
		echo "Warning: CSV file 'Rooms_PUBLISHER_HTML-ICS(in).csv' not found - skipping enforce_csv_full_update"
	fi

	echo "Setup complete"

	# Ensure app files are owned by the non-root runtime user so Playwright and
	# the application can access installed browser binaries and caches.
	chown -R appuser:appuser /app || true

	# Auto-start detached full extraction if not already running and there are enabled calendars
	PIDFILE=/app/playwright_captures/extract_detached.pid
	echo "Checking for existing detached extractor..."
	if [ -f "$PIDFILE" ]; then
		PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
		if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
			echo "Detached extractor already running with PID $PID"
		else
			echo "Stale or empty pidfile found, removing"
			rm -f "$PIDFILE" || true
		fi
	fi

	# Start extractor if no pidfile and calendars exist (or CSV was found earlier)
	if [ ! -f "$PIDFILE" ]; then
		echo "No detached extractor running; checking DB for enabled calendars..."
		# Use a small helper script so Python runs from a file (avoids __file__ issues)
		if python3 -c "import sys" >/dev/null 2>&1; then
			ENABLED_COUNT=$(python3 /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
		else
			ENABLED_COUNT=$(python /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
		fi
		echo "Enabled calendars in DB: ${ENABLED_COUNT}"
		if [ "${ENABLED_COUNT}" -gt 0 ]; then
			echo "Starting detached full extraction as appuser..."
			su -s /bin/bash appuser -c "mkdir -p /app/playwright_captures && nohup python3 /app/tools/run_full_extraction.py > /app/playwright_captures/extract_stdout.txt 2>/app/playwright_captures/extract_stderr.txt & echo \$! > /app/playwright_captures/extract_detached.pid" || true
			echo "Detached extractor started, pidfile: $PIDFILE"
		else
			echo "No enabled calendars found - skipping detached extraction start"
		fi
	fi

	# Drop privileges to `appuser` when launching the main process so Playwright
	# runs with the same user that installed browsers during image build.
	# Use `su` to run the provided command as appuser. This preserves the
	# existing behavior but ensures the runtime user has the expected home
	# directory and cache paths.
	exec su -s /bin/bash appuser -c "$*"