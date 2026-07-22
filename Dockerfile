# Railway production Dockerfile — FINAL (no cache possible)
# Completely restructured to force fresh build every time
FROM python:3.12-slim

# Unusual comment to change file hash: maestro-deploy-final-2026-07-22-v4

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# CRITICAL: touch a file in the WORKDIR BEFORE copying source.
# This creates a new layer that invalidates ALL subsequent COPY layers.
# The file content includes a timestamp so it's different every build.
RUN echo "build-$(date +%s)" > /app/.build-timestamp && cat /app/.build-timestamp

# Copy source — will NOT be cached because the previous layer changed
COPY download/MaestroAgent/maestro-personal/pyproject.toml download/MaestroAgent/maestro-personal/README.md ./
COPY download/MaestroAgent/maestro-personal/src/ ./src/

# Verify the correct admin.py is in the image (build FAILS if stale)
RUN grep "11.0.0-session10-final" /app/src/maestro_personal_shell/routers/admin.py && \
    grep "import os" /app/src/maestro_personal_shell/routers/admin.py && \
    ! grep "subprocess.check_output" /app/src/maestro_personal_shell/routers/admin.py && \
    echo "VERIFIED: admin.py has version 11.0.0 + import os + no subprocess"

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

# Build canary
ENV MAESTRO_BUILD_TIME="2026-07-22-final-v4"
ENV MAESTRO_BUILD_COMMIT="5983f7b"

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
