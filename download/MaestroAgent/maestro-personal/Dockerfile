FROM python:3.12-slim

WORKDIR /app

# Install system deps for SQLite + crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements + source together (pip install -e needs src/ to exist
# because pyproject.toml says packages.find where = ["src"])
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY .z-ai-config ./

# Install (non-editable — no need for -e in production)
RUN pip install --no-cache-dir "."

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_ENV=production

# Railway injects PORT automatically — don't hardcode EXPOSE.
# The app reads PORT env var (see api.py line 42).

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
