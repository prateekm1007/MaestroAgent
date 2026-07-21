# Railway production Dockerfile — Session 10 final
# Build context = repo root (Railway Root Directory = repo root)
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy maestro-personal source (build context = repo root)
COPY download/MaestroAgent/maestro-personal/pyproject.toml download/MaestroAgent/maestro-personal/README.md ./
COPY download/MaestroAgent/maestro-personal/src/ ./src/

# Copy backend maestro_* packages
COPY download/MaestroAgent/backend/maestro_cognitive_council/ ./src/maestro_cognitive_council/
COPY download/MaestroAgent/backend/maestro_llm/               ./src/maestro_llm/
COPY download/MaestroAgent/backend/maestro_nerve/             ./src/maestro_nerve/
COPY download/MaestroAgent/backend/maestro_oem/               ./src/maestro_oem/
COPY download/MaestroAgent/backend/maestro_db/                ./src/maestro_db/
COPY download/MaestroAgent/backend/maestro_api/               ./src/maestro_api/
COPY download/MaestroAgent/backend/maestro_auth/              ./src/maestro_auth/
COPY download/MaestroAgent/backend/maestro_core/              ./src/maestro_core/
COPY download/MaestroAgent/backend/maestro_memory/            ./src/maestro_memory/
COPY download/MaestroAgent/backend/maestro_plugins/           ./src/maestro_plugins/
COPY download/MaestroAgent/backend/maestro_verify/            ./src/maestro_verify/

# Install (match proven working config — NOT -e ".[dev]")
RUN pip install --no-cache-dir "." "sqlalchemy>=2.0"

# Embed build-time canary (unforgeable version string)
ENV MAESTRO_BUILD_TIME="2026-07-22-session10-final"
ENV MAESTRO_BUILD_COMMIT="fffb0f5"

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
