FROM python:3.12-slim

WORKDIR /app

# Install system deps for SQLite + crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# P-2026-07-18 fix: build context is now the repo root (download/MaestroAgent),
# not maestro-personal/. This allows us to also COPY the backend maestro_*
# packages that maestro_personal_shell imports (maestro_cognitive_council,
# maestro_llm, maestro_nerve, maestro_oem + transitive deps). Without this,
# /api/ask crashed with `ModuleNotFoundError: No module named
# 'maestro_cognitive_council'` because surfaces/ask.py imports it but the
# package was never installed in the Docker image.
#
# Railways service config: rootDirectory = "download/MaestroAgent"
# (was: "download/MaestroAgent/maestro-personal")

# Copy maestro-personal source (build context = repo root)
COPY maestro-personal/pyproject.toml maestro-personal/README.md ./
COPY maestro-personal/src/ ./src/

# Copy backend maestro_* packages that maestro_personal_shell imports
# (transitive closure: maestro_cognitive_council, maestro_llm, maestro_nerve,
# maestro_oem, maestro_db, maestro_api, maestro_auth, maestro_core,
# maestro_memory, maestro_plugins, maestro_verify)
# These get placed in src/ so setuptools.packages.find (where=["src"])
# discovers and installs them alongside maestro_personal_shell.
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

# Install maestro-personal (which will pick up all packages in src/ via
# setuptools.packages.find). Also install sqlalchemy explicitly because
# maestro_db / maestro_api import it but maestro-personal's pyproject.toml
# does not list it as a dep.
RUN pip install --no-cache-dir "." "sqlalchemy>=2.0"

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

# Railway injects PORT automatically — don't hardcode EXPOSE.
# The app reads PORT env var (see api.py line 42).

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
