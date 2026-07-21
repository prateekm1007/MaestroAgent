# Railway production Dockerfile — placed at repo root so Railway can find it
# Build context = repo root, so paths are relative to /
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy from download/MaestroAgent/ (the actual app directory)
COPY download/MaestroAgent/maestro-personal/pyproject.toml download/MaestroAgent/maestro-personal/README.md ./
COPY download/MaestroAgent/maestro-personal/src/ ./src/

# Copy backend maestro_* packages
COPY download/MaestroAgent/backend/maestro_cognitive_council/ ./src/maestro_cognitive_council/
COPY download/MaestroAgent/backend/maestro_llm/ ./src/maestro_llm/
COPY download/MaestroAgent/backend/maestro_oem/ ./src/maestro_oem/
COPY download/MaestroAgent/backend/maestro_api/ ./src/maestro_api/
COPY download/MaestroAgent/backend/maestro_auth/ ./src/maestro_auth/
COPY download/MaestroAgent/backend/maestro_core/ ./src/maestro_core/
COPY download/MaestroAgent/backend/maestro_db/ ./src/maestro_db/
COPY download/MaestroAgent/backend/maestro_memory/ ./src/maestro_memory/
COPY download/MaestroAgent/backend/maestro_nerve/ ./src/maestro_nerve/
COPY download/MaestroAgent/backend/maestro_plugins/ ./src/maestro_plugins/
COPY download/MaestroAgent/backend/maestro_verify/ ./src/maestro_verify/

# Install
RUN pip install -e ".[dev]" --no-cache-dir

EXPOSE 8766
CMD ["python", "-m", "maestro_personal_shell.api"]
