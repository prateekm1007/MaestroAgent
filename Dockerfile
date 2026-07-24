# Railway production — cache-busts on every deploy via CACHEBUST build-arg
FROM python:3.12-slim AS builder

WORKDIR /build
# CACHEBUST must be USED in a RUN command to actually invalidate the layer.
# Declaring ARG without using it does nothing — that was the prior bug.
ARG CACHEBUST
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*

# Copy source. The maestro-personal/src/ goes to /build/src/ (for pip install).
# The 4 used backend modules go to /build/src/ too (PYTHONPATH=/app/src at runtime).
# The other 6 backend modules are NOT copied (dead weight).
COPY download/MaestroAgent/maestro-personal/pyproject.toml \
     download/MaestroAgent/maestro-personal/README.md \
     ./
COPY download/MaestroAgent/maestro-personal/src/ \
     ./src/
COPY download/MaestroAgent/backend/maestro_cognitive_council/ \
     ./src/maestro_cognitive_council/
COPY download/MaestroAgent/backend/maestro_llm/ \
     ./src/maestro_llm/
COPY download/MaestroAgent/backend/maestro_db/ \
     ./src/maestro_db/
COPY download/MaestroAgent/backend/maestro_nerve/ \
     ./src/maestro_nerve/
COPY download/MaestroAgent/backend/maestro_oem/ \
     ./src/maestro_oem/

# Verify admin.py is correct (build FAILS if stale)
RUN grep "MAESTRO_VERSION" /build/src/maestro_personal_shell/routers/admin.py && \
    grep "import os" /build/src/maestro_personal_shell/routers/admin.py && \
    echo "VERIFIED"

# Install into the build stage.
# Explicit email-validator + slowapi are belt-and-suspenders: they're already in
# pyproject.toml, but listing them here guarantees the install layer hash changes
# when the build-arg changes (CACHEBUST echoed into the layer).
RUN echo "CACHEBUST=${CACHEBUST:-unset}" && \
    pip install --no-cache-dir "." "sqlalchemy>=2.0" "email-validator>=2.0" "slowapi>=0.1.9" "google-api-python-client>=2.100.0" "google-auth-oauthlib>=1.1.0" "google-auth-httplib2>=0.2.0"

# Final stage — fresh image, no cache possible
FROM python:3.12-slim
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy source
COPY --from=builder /build/ ./

# Build identity — single source of truth.
# R-traceability fix (reviewer): the commit SHA is now injected at build time
# via BUILD_COMMIT arg. This ensures /api/health always reports the actual
# deployed commit, not a stale hardcoded value.
ARG BUILD_COMMIT=unknown
ARG BUILD_TIME=unknown
ENV MAESTRO_VERSION="1.0.0-beta"
ENV MAESTRO_BUILD_COMMIT=$BUILD_COMMIT
ENV MAESTRO_BUILD_TIME=$BUILD_TIME
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=production

CMD ["python", "-m", "maestro_personal_shell.api"]
