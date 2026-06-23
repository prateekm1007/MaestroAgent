# MaestroAgent sandbox image.
#
# This is the default container used by `maestro_verify.sandbox.run_in_sandbox`
# to execute tool calls, tests, and lint commands in isolation.
#
# Design principles:
# - Minimal: only the tools needed for coding/research workflows.
# - Read-only root at runtime (the engine mounts /workspace as a writable volume).
# - No network by default (the engine passes --network none unless an
#   egress allowlist is configured).
# - Runs as `nobody` to limit privilege.
#
# Build:
#   docker build -t maestroagent/sandbox:latest backend/sandbox/
#
# Or via docker-compose (see docs/SETUP.md).

FROM ubuntu:24.04

LABEL org.opencontainers.image.title="MaestroAgent Sandbox"
LABEL org.opencontainers.image.description="Isolated execution environment for MaestroAgent tool calls"
LABEL org.opencontainers.image.source="https://github.com/your-org/maestroagent"
LABEL org.opencontainers.image.licenses="MIT"

# Avoid interactive prompts during apt install.
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Core tools: git, curl, jq, build essentials, Python 3, Node 20, Docker CLI.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    git \
    jq \
    unzip \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    nodejs \
    npm \
    docker.io \
    openssh-client \
    gnupg \
    ripgrep \
    fd-find \
    fzf \
    less \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*

# Install common Python tools the engine expects.
RUN pip3 install --no-cache-dir --break-system-packages \
    pytest \
    ruff \
    mypy \
    black \
    pipx

# Install pnpm (for Node workflows).
RUN npm install -g pnpm

# Create a non-root user for tool execution.
# The engine runs commands as `nobody` by default.
RUN mkdir -p /workspace /tmp/maestro && \
    chown -R nobody:nogroup /workspace /tmp/maestro

WORKDIR /workspace

# The entrypoint just sleeps — the engine `docker exec`s into the
# container to run individual commands.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER nobody

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
