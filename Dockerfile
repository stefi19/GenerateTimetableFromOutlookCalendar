# AC UTCN Timetable Viewer
# Multi-stage build for optimized production image
# Tuned for 32 GB RAM / 16 vCPU

# ============================================
# Stage 1: Build React Frontend
# ============================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files first (layer cache)
COPY frontend/package*.json ./

# Install dependencies with npm ci for reproducibility
RUN npm ci --only=production=false

# Copy frontend source
COPY frontend/ ./

# Build production bundle (Vite)
RUN npm run build

# ============================================
# Stage 2: Python Runtime (optimized for 32GB/16vCPU)
# ============================================
FROM python:3.12-slim-bookworm AS runtime

# Set environment variables for performance
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=5000 \
    # pip parallelism
    PIP_NO_CACHE_DIR=1 \
    # Python memory allocator tuning
    PYTHONMALLOC=pymalloc \
    MALLOC_ARENA_MAX=4 \
    # Reduce glibc malloc fragmentation for multi-threaded apps
    MALLOC_MMAP_THRESHOLD_=131072 \
    MALLOC_TRIM_THRESHOLD_=131072

WORKDIR /app

# Install system dependencies for Playwright + performance tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Performance: dumb-init for proper signal handling with gunicorn
    dumb-init \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Create non-root user for security BEFORE installing Playwright
RUN useradd --create-home --shell /bin/bash appuser

# Install Playwright browsers as appuser (so cache is in their home)
USER appuser
RUN playwright install chromium
USER root

# Copy application code
COPY app.py timetable.py ./
COPY templates/ templates/
COPY tools/ tools/
COPY config/ config/
COPY static/ static/
COPY entrypoint.sh ./

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist/ frontend/dist/

# Create data directories and set ownership
RUN mkdir -p data playwright_captures \
    && chown -R appuser:appuser /app \
    && chmod +x entrypoint.sh

USER appuser

# Expose port
EXPOSE 5000

# Health check (with longer start period for large deployments)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Use dumb-init for proper PID 1 signal handling (clean gunicorn shutdown)
# Gunicorn config is driven by environment variables in entrypoint.sh
ENTRYPOINT ["dumb-init", "--", "./entrypoint.sh"]
CMD ["gunicorn"]
