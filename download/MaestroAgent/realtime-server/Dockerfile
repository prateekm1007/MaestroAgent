# =============================================================================
# Maestro — Production Dockerfile (API server + worker)
# Multi-stage build: build step → minimal runtime
# =============================================================================

FROM node:22-slim AS builder

WORKDIR /app

# Copy package files
COPY realtime-server/package*.json ./
COPY realtime-server/package-lock.json* ./

# Install all dependencies (including dev)
RUN npm ci

# Copy source
COPY realtime-server/ ./

# Build (no build step for plain JS, but ensures dependencies are correct)
RUN npm ls --depth=0

# =============================================================================
# Runtime image
# =============================================================================

FROM node:22-slim AS runtime

# Install dumb-init for proper signal handling
RUN apt-get update && apt-get install -y --no-install-recommends dumb-init curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package files and install production dependencies only
COPY realtime-server/package*.json ./
COPY realtime-server/package-lock.json* ./
RUN npm ci --omit=dev

# Copy built source from builder
COPY --from=builder /app/src ./src
COPY --from=builder /app/migrations ./migrations
COPY --from=builder /app/scripts ./scripts
COPY realtime-server/server.js ./
COPY realtime-server/vitest.config.js ./

# Create directories
RUN mkdir -p /app/deliverables /app/keys /app/backups

# Set environment
ENV NODE_ENV=production
ENV PORT=8765
ENV DATABASE_URL=postgresql://maestro:maestro@db:5432/maestro

# Expose port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8765/api/health || exit 1

# Use dumb-init for proper PID 1 signal handling
ENTRYPOINT ["dumb-init", "--"]

# Default: run API server
CMD ["node", "server.js"]
