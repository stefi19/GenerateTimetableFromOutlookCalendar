#!/bin/bash
# deploy.sh - Script for updating the app on VM without losing data
# Usage: ./deploy.sh

set -e

echo "=== UTCN Timetable Deployment ==="

# Pull latest code
echo "📥 Pulling latest code..."
git pull origin main

# Rebuild and restart containers (volumes preserve data!)
echo "🔨 Rebuilding Docker image..."
docker compose down
docker compose build --no-cache
docker compose up -d

# Show status
echo ""
echo "✅ Deployment complete!"
echo ""
docker compose ps
echo ""
echo "📊 Data volumes (preserved):"
docker volume ls | grep timetable || echo "  (volumes will be created on first run)"
echo ""
echo "🔗 App running at: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
