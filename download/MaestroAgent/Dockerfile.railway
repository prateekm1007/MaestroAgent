# Railway Dockerfile — build context root is download/MaestroAgent/
# Paths are relative to this directory (NOT the repo root)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev git \
    && rm -rf /var/lib/apt/lists/*

# Copy from maestro-personal/ (relative to download/MaestroAgent/)
COPY maestro-personal/pyproject.toml maestro-personal/README.md ./
COPY maestro-personal/src/ ./src/

# Copy backend maestro_* packages (relative to download/MaestroAgent/)
COPY backend/maestro_cognitive_council/ ./src/maestro_cognitive_council/
COPY backend/maestro_llm/ ./src/maestro_llm/
COPY backend/maestro_oem/ ./src/maestro_oem/
COPY backend/maestro_api/ ./src/maestro_api/
COPY backend/maestro_auth/ ./src/maestro_auth/
COPY backend/maestro_core/ ./src/maestro_core/
COPY backend/maestro_db/ ./src/maestro_db/
COPY backend/maestro_memory/ ./src/maestro_memory/
COPY backend/maestro_nerve/ ./src/maestro_nerve/
COPY backend/maestro_plugins/ ./src/maestro_plugins/
COPY backend/maestro_verify/ ./src/maestro_verify/

# Install
RUN pip install -e ".[dev]" --no-cache-dir

EXPOSE 8766
CMD ["python", "-m", "maestro_personal_shell.api"]
