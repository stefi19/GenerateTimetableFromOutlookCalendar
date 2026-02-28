#!/bin/bash
set -e

# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint for UTCN Timetable container
# Optimized for 32 GB RAM / 16 vCPU
# ─────────────────────────────────────────────────────────────────────────────

# Raise the soft/hard nofile limit for the current shell so child processes
# inherit a higher file descriptor limit.
ulimit -n 65536 || true

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  UTCN Timetable - Starting (32GB/16vCPU optimized)         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# ── Database setup ──
echo "⏳ Running database setup..."
python3 /app/tools/init_db.py || true

# ── Populate calendars from CSV (if present) ──
echo "⏳ Populating calendars from CSV..."
CSV_CANDIDATES=(
    "/app/config/Rooms_PUBLISHER_HTML-ICS(in).csv"
    "/app/Rooms_PUBLISHER_HTML-ICS(in).csv"
    "/app/playwright_captures/Rooms_PUBLISHER_HTML-ICS(in).csv"
)
CSV_FOUND=0
for p in "${CSV_CANDIDATES[@]}"; do
    if [ -f "$p" ]; then
        echo "  ✓ Found CSV at $p"
        cd /app && python3 tools/populate_calendars_from_csv.py || true
        CSV_FOUND=1
        break
    fi
done
if [ "$CSV_FOUND" -eq 0 ]; then
    echo "  ⚠ CSV not found - skipping population step"
fi

# ── Update with emails, names, buildings ──
echo "⏳ Updating calendars with CSV data..."
for p in "${CSV_CANDIDATES[@]}"; do
    if [ -f "$p" ]; then
        echo "  ✓ Running enforce_csv_full_update"
        cd /app && python3 tools/enforce_csv_full_update.py || true
        break
    fi
done

echo "✅ Setup complete"

# Ensure app files are owned by the non-root runtime user
chown -R appuser:appuser /app || true

# ── Auto-start detached full extraction ──
PIDFILE=/app/playwright_captures/extract_detached.pid
echo "⏳ Checking for existing detached extractor..."
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "  ✓ Detached extractor already running with PID $PID"
    else
        echo "  ⚠ Stale pidfile found, removing"
        rm -f "$PIDFILE" || true
    fi
fi

if [ ! -f "$PIDFILE" ]; then
    ENABLED_COUNT=$(python3 /app/tools/get_enabled_count.py 2>/dev/null || echo 0)
    echo "  Enabled calendars in DB: ${ENABLED_COUNT}"
    if [ "${ENABLED_COUNT}" -gt 0 ]; then
        echo "  🚀 Starting detached full extraction as appuser..."
        su -s /bin/bash appuser -c "cd /app && mkdir -p /app/playwright_captures && nohup python3 /app/tools/run_full_extraction.py > /app/playwright_captures/extract_stdout.txt 2>/app/playwright_captures/extract_stderr.txt & echo \$! > /app/playwright_captures/extract_detached.pid" || true
        echo "  ✓ Detached extractor started"
    else
        echo "  ⚠ No enabled calendars - skipping extraction"
    fi
fi

# ── Launch main process ──
# If the command is "gunicorn", build the full gunicorn command with
# environment-driven performance tuning for 32GB/16vCPU.
if [ "$1" = "gunicorn" ]; then
    WORKERS="${GUNICORN_WORKERS:-8}"
    THREADS="${GUNICORN_THREADS:-4}"
    WORKER_CLASS="${GUNICORN_WORKER_CLASS:-gthread}"
    TIMEOUT="${GUNICORN_TIMEOUT:-180}"
    KEEPALIVE="${GUNICORN_KEEPALIVE:-5}"
    MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-2000}"
    MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-200}"

    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Gunicorn Config:                                          ║"
    echo "║  Workers: $WORKERS | Threads/worker: $THREADS | Class: $WORKER_CLASS"
    echo "║  Timeout: ${TIMEOUT}s | Keep-alive: ${KEEPALIVE}s"
    echo "║  Max requests: $MAX_REQUESTS (jitter: $MAX_REQUESTS_JITTER)"
    echo "║  Total concurrent slots: $((WORKERS * THREADS))"
    echo "╚══════════════════════════════════════════════════════════════╝"

    exec su -s /bin/bash appuser -c "exec gunicorn \
        --bind 0.0.0.0:5000 \
        --workers $WORKERS \
        --threads $THREADS \
        --worker-class $WORKER_CLASS \
        --timeout $TIMEOUT \
        --keep-alive $KEEPALIVE \
        --max-requests $MAX_REQUESTS \
        --max-requests-jitter $MAX_REQUESTS_JITTER \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        --preload \
        --forwarded-allow-ips='*' \
        app:app"
else
    # Fallback: run whatever command was passed
    exec su -s /bin/bash appuser -c "$*"
fi
