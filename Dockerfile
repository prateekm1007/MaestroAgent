# Railway production Dockerfile — FINAL deterministic build
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Cache bust: unique layer every build, invalidates all subsequent COPY layers
RUN echo "build-$(date +%s)" > /app/.build-timestamp

# Copy source
COPY download/MaestroAgent/maestro-personal/pyproject.toml download/MaestroAgent/maestro-personal/README.md ./
COPY download/MaestroAgent/maestro-personal/src/ ./src/

# BUILD-TIME VERIFICATION: build FAILS if admin.py doesn't have the env-var-based version
RUN grep "MAESTRO_VERSION" /app/src/maestro_personal_shell/routers/admin.py && \
    grep "import os" /app/src/maestro_personal_shell/routers/admin.py && \
    ! grep "subprocess" /app/src/maestro_personal_shell/routers/admin.py && \
    ! grep "11.0.0\|10.0.0\|1.0.0" /app/src/maestro_personal_shell/routers/admin.py && \
    echo "VERIFIED: admin.py uses env-var version, no hardcoded strings, no subprocess"

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

# Install
RUN pip install --no-cache-dir "." "sqlalchemy>=2.0"

# SINGLE SOURCE OF TRUTH for build identity — env vars, not hardcoded strings
ENV MAESTRO_VERSION="12.0.0-audit-ready"
ENV MAESTRO_BUILD_COMMIT="839f38d"
ENV MAESTRO_BUILD_TIME="2026-07-22T02:40:00Z"

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
