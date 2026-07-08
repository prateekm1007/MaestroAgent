# Round 49 C6 fix: Dockerfile rewritten for actual production assets.
# The old Dockerfile referenced frontend/, realtime-server/, frontend-next/
# directories that only exist under _deprecated/. This version copies the
# actual vanilla JS app (app.html + static/).
#
# Build:
#   docker build -t maestroagent/app:latest .
#
# Run (dev):
#   docker run -p 8765:8765 -e MAESTRO_DEMO_SEED=true maestroagent/app:latest
#
# Run (production):
#   docker run -p 8765:8765 \
#     -e MAESTRO_ENV=production \
#     -e MAESTRO_DEMO_SEED=false \
#     -e JWT_SECRET=$JWT_SECRET \
#     -e MAESTRO_MASTER_KEY=$MAESTRO_MASTER_KEY \
#     -e MAESTRO_ADMIN_PASSWORD=$MAESTRO_ADMIN_PASSWORD \
#     -e MAESTRO_AUTH_ENABLED=true \
#     -e MAESTRO_AUTH_DB=/data/auth.db \
#     -v maestro-data:/data \
#     maestroagent/app:latest

FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libxml2-dev libxslt-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 maestro
WORKDIR /app

# Copy backend and install
COPY backend/ /app/backend/
RUN pip install --no-cache-dir -e /app/backend

# Copy frontend (the actual vanilla JS app — NOT _deprecated/frontend)
COPY app.html /app/
COPY static/ /app/static/
COPY CONSTITUTION.md /app/

# Set ownership
RUN chown -R maestro:maestro /app

# Round 65 CTO Blocker 4: create /data BEFORE switching to non-root user.
# The old code ran `mkdir -p /data` after `USER maestro` — non-root cannot
# create directories in root-owned /. This caused `docker build` to fail.
RUN mkdir -p /data && chown maestro:maestro /data

# Switch to non-root user
USER maestro

# Environment defaults (dev mode)
ENV MAESTRO_APP_DIR=/app
ENV MAESTRO_DEMO_SEED=true
ENV PYTHONPATH=/app/backend
ENV MAESTRO_AUTH_DB=/data/auth.db

EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/health')" || exit 1

CMD ["uvicorn", "maestro_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765"]
