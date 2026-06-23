# Multi-stage Dockerfile for MaestroAgent — browser-first self-hosting.
#
# Stage 1: Build the React PWA bundle.
# Stage 2: Build the Python backend + serve the PWA.
#
# Result: a single container that serves the installable PWA at /
# and the API at /api. One `docker run` is all you need.
#
# Build:
#   docker build -t maestroagent/app:latest .
#
# Run:
#   docker run -p 8765:8765 -v maestro-data:/data maestroagent/app:latest
#
# Then open http://localhost:8765 in Chrome/Firefox/Brave and click
# "Install" in the address bar to install as a PWA.

# ---------- Stage 1: Frontend ----------
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Install pnpm.
RUN npm install -g pnpm

# Copy package files and install deps.
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

# Copy source and build.
COPY frontend/ ./
RUN pnpm build

# ---------- Stage 2: Backend ----------
FROM python:3.11-slim AS backend

WORKDIR /app

# Install system deps for Python packages (chromadb needs some build tools).
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
COPY backend/examples/ ./examples/
COPY backend/plugins/ ./plugins/

RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Copy the built frontend dist into the container.
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create data directory for persistent storage.
RUN mkdir -p /data /workspace
ENV MAESTRO_FRONTEND_DIST=/app/frontend/dist
ENV MAESTRO_DB_PATH=/data/maestro.db
ENV MAESTRO_CHROMA_PATH=/data/chroma
ENV MAESTRO_GRAPH_PATH=/data/graph.json

# Expose the single port the PWA + API share.
EXPOSE 8765

# Volume for persistent data (SQLite DB, Chroma, graph).
VOLUME ["/data", "/workspace"]

# Health check — verify the API is responding.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8765/api/health || exit 1

# Run the backend, which serves both the API and the PWA bundle.
CMD ["python", "-m", "maestro_cli.main", "serve", "--host", "0.0.0.0", "--port", "8765", "--db-path", "/data/maestro.db"]
