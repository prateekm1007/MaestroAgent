# Railway Dockerfile — build context root is download/MaestroAgent/
# Paths are relative to this directory (NOT the repo root)
# Session 10: this is the CORRECT Dockerfile for Railway's Root Directory setting
FROM python:3.12-slim

WORKDIR /app

# Install system deps for SQLite + crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy maestro-personal source (build context = download/MaestroAgent/)
COPY maestro-personal/pyproject.toml maestro-personal/README.md ./
COPY maestro-personal/src/ ./src/

# Copy backend maestro_* packages that maestro_personal_shell imports
COPY backend/maestro_cognitive_council/ ./src/maestro_cognitive_council/
COPY backend/maestro_llm/               ./src/maestro_llm/
COPY backend/maestro_nerve/             ./src/maestro_nerve/
COPY backend/maestro_oem/               ./src/maestro_oem/
COPY backend/maestro_db/                ./src/maestro_db/
COPY backend/maestro_api/               ./src/maestro_api/
COPY backend/maestro_auth/              ./src/maestro_auth/
COPY backend/maestro_core/              ./src/maestro_core/
COPY backend/maestro_memory/            ./src/maestro_memory/
COPY backend/maestro_plugins/           ./src/maestro_plugins/
COPY backend/maestro_verify/            ./src/maestro_verify/

# Install maestro-personal (picks up all packages in src/ via setuptools)
# Also install sqlalchemy explicitly (maestro_db/maestro_api need it)
RUN pip install --no-cache-dir "." "sqlalchemy>=2.0"

# Embed build-time canary (auditor F-NEW-2: version string must be unforgeable)
ENV MAESTRO_BUILD_TIME="2026-07-22-session10-final"
ENV MAESTRO_BUILD_COMMIT="806a1c3"

# Environment — MUST match the proven working config
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
