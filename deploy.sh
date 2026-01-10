#!/usr/bin/env bash
# deploy.sh - Comprehensive deployment script for the UTCN timetable app
# - pulls latest code, rebuilds images, starts containers
# - waits for app health, runs a full extraction and a single worker merge pass
# - shows useful status and logs
# Usage: ./deploy.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=== UTCN Timetable Full Deploy ==="

# Configurable flags (export or edit if you want to change defaults)
DO_PRUNE=${DO_PRUNE:-false}                 # set true to prune unused images
RUN_FULL_EXTRACTION=${RUN_FULL_EXTRACTION:-true}
RUN_WORKER_ONCE=${RUN_WORKER_ONCE:-true}
WAIT_FOR_HEALTH=${WAIT_FOR_HEALTH:-true}
HEALTH_WAIT_SECONDS=${HEALTH_WAIT_SECONDS:-60}

echo "📥 Pulling latest code from git..."
git pull origin main

echo "🔧 Stopping existing containers (preserve volumes)..."
docker compose down --remove-orphans || true

if [ "$DO_PRUNE" = "true" ]; then
	echo "🧹 Pruning unused images and containers..."
	docker system prune -f || true
fi

echo "🔨 Building Docker images (no-cache)..."
docker compose build --no-cache

echo "🚀 Starting containers..."
docker compose up -d

if [ "$WAIT_FOR_HEALTH" = "true" ]; then
	echo "⏳ Waiting up to ${HEALTH_WAIT_SECONDS}s for app health (http://localhost:5000/health)"
	elapsed=0
	until curl -sSf http://localhost:5000/health >/dev/null 2>&1 || [ $elapsed -ge $HEALTH_WAIT_SECONDS ]; do
		sleep 2
		elapsed=$((elapsed+2))
		printf '.'
	done
	if curl -sSf http://localhost:5000/health >/dev/null 2>&1; then
		echo "\n✅ App is healthy"
	else
		echo "\n⚠️ App did not report healthy within ${HEALTH_WAIT_SECONDS}s; check logs"
	fi
fi

# Run the long-running full extraction (populate per-calendar files) inside container
if [ "$RUN_FULL_EXTRACTION" = "true" ]; then
	echo "🔁 Running full extraction for all enabled calendars (this may take long)..."
	# Run inside the timetable service container so environment and Playwright are available
	docker compose exec -T timetable sh -c 'export PYTHONUTF8=1; python3 tools/run_full_extraction.py'
	echo "✅ Full extraction finished (check playwright_captures/*.json)"
fi

# Run the worker once to merge future events/preserved past and rebuild schedule
if [ "$RUN_WORKER_ONCE" = "true" ]; then
	echo "🔧 Running worker once (merge future events, rebuild schedule)..."
	docker compose exec -T timetable sh -c 'export PYTHONUTF8=1; RUN_ONCE=1 python3 tools/worker_update_future.py'
	echo "✅ Worker RUN_ONCE finished"
fi

echo ""
echo "📦 Docker compose status:"
docker compose ps

echo ""
echo "📄 Last schedule file info (playwright_captures/schedule_by_room.json):"
docker compose exec -T timetable sh -c 'ls -lh playwright_captures/schedule_by_room.json || true'

echo ""
echo "📋 Tail of application logs (last 200 lines):"
docker compose logs --no-color --tail=200

echo ""
echo "✅ Deployment script finished. Visit: http://localhost:5000/"
echo "Admin panel (legacy/React): http://localhost:5000/admin (protected by ADMIN_PASSWORD)"
echo "" 
