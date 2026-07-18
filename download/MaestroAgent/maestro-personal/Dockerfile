FROM python:3.12-slim

WORKDIR /app

# Install system deps for SQLite + crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source
COPY src/ ./src/
COPY tests/ ./tests/

# Environment
ENV PYTHONPATH=/app/src
ENV MAESTRO_ENV=production
ENV PORT=8766

# Expose port
EXPOSE 8766

# Start
CMD ["python", "-m", "maestro_personal_shell.api"]
