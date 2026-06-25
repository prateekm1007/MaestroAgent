# Multi-stage Dockerfile for MaestroAgent v1.0 — browser-first self-hosting.
#
# Security hardening (v1.0):
# - Multi-stage build (small attack surface)
# - Non-root user in the final image
# - Read-only filesystem where possible
# - Resource limits set via docker-compose
# - No secrets baked into the image
#
# Build:
#   docker build -t maestroagent/app:1.0.0 .
#
# Run:
#   docker run -p 8765:8765 -v maestro-data:/data maestroagent/app:1.0.0
#
# For production (with auth + HTTPS):
#   docker run -p 8765:8765 -v maestro-data:/data \
#     -e MAESTRO_AUTH_ENABLED=true \
#     -e MAESTRO_CORS_ORIGINS=https://maestro.yourdomain.com \
#     maestroagent/app:1.0.0

# ---------- Stage 1: Frontend ----------
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
RUN npm install -g pnpm
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY frontend/ ./
RUN pnpm build

# ---------- Stage 2: Backend ----------
FROM python:3.11-slim AS backend

WORKDIR /app

# Install system deps for Python packages + curl for healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy backend and install.
COPY backend/pyproject.toml backend/
COPY backend/maestro_core/ ./maestro_core/
COPY backend/maestro_agents/ ./maestro_agents/
COPY backend/maestro_loops/ ./maestro_loops/
COPY backend/maestro_memory/ ./maestro_memory/
COPY backend/maestro_verify/ ./maestro_verify/
COPY backend/maestro_llm/ ./maestro_llm/
COPY backend/maestro_api/ ./maestro_api/
COPY backend/maestro_plugins/ ./maestro_plugins/
COPY backend/maestro_cli/ ./maestro_cli/
COPY backend/maestro_hybrid/ ./maestro_hybrid/
COPY backend/maestro_auth/ ./maestro_auth/
COPY backend/maestro_meta/ ./maestro_meta/
COPY backend/examples/ ./examples/
COPY backend/plugins/ ./plugins/

RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy the built frontend dist into the container.
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create a non-root user for the app to run as.
RUN groupadd -r maestro && useradd -r -g maestro -d /app -s /sbin/nologin maestro \
    && mkdir -p /data /workspace \
    && chown -R maestro:maestro /app /data /workspace

# Switch to the non-root user.
USER maestro

# Environment.
ENV MAESTRO_FRONTEND_DIST=/app/frontend/dist
ENV MAESTRO_DB_PATH=/data/maestro.db
ENV MAESTRO_CHROMA_PATH=/data/chroma
ENV MAESTRO_GRAPH_PATH=/data/graph.json
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765

# Volume for persistent data.
VOLUME ["/data", "/workspace"]

# Health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8765/api/health || exit 1

# Run the backend (serves both API + PWA bundle).
# uvicorn with 1 worker (scale horizontally via docker compose --scale).
CMD ["python", "-m", "maestro_cli.main", "serve", "--host", "0.0.0.0", "--port", "8765", "--db-path", "/data/maestro.db"]
