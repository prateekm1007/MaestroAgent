# Railway production — cache-busts on every deploy via CACHEBUST build-arg
FROM python:3.12-slim AS builder

WORKDIR /build
# CACHEBUST must be USED in a RUN command to actually invalidate the layer.
# Declaring ARG without using it does nothing — that was the prior bug.
ARG CACHEBUST
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*

# Single COPY of ALL source at once (different structure = different cache key)
COPY download/MaestroAgent/maestro-personal/pyproject.toml \
     download/MaestroAgent/maestro-personal/README.md \
     download/MaestroAgent/maestro-personal/src/ \
     download/MaestroAgent/backend/ \
     ./

# Verify admin.py is correct (build FAILS if stale)
RUN grep "MAESTRO_VERSION" /build/maestro_personal_shell/routers/admin.py && \
    grep "import os" /build/maestro_personal_shell/routers/admin.py && \
    echo "VERIFIED"

# Install into the build stage.
# Explicit email-validator + slowapi are belt-and-suspenders: they're already in
# pyproject.toml, but listing them here guarantees the install layer hash changes
# when the build-arg changes (CACHEBUST echoed into the layer).
RUN echo "CACHEBUST=${CACHEBUST:-unset}" && \
    pip install --no-cache-dir "." "sqlalchemy>=2.0" "email-validator>=2.0" "slowapi>=0.1.9"

# Final stage — fresh image, no cache possible
FROM python:3.12-slim
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy source
COPY --from=builder /build/ ./

# Build identity — single source of truth
ENV MAESTRO_VERSION="12.0.0-audit-ready"
ENV MAESTRO_BUILD_COMMIT="d629818"
ENV MAESTRO_BUILD_TIME="2026-07-22T05:07:00Z"
ENV PYTHONPATH=/app/src
ENV MAESTRO_PERSONAL_ENV=dev

CMD ["python", "-m", "maestro_personal_shell.api"]
