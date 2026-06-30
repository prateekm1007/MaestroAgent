# =============================================================================
# Maestro — Frontend Dockerfile (Next.js)
# =============================================================================

FROM node:22-slim AS builder

WORKDIR /app

COPY frontend-next/package*.json ./
RUN npm ci

COPY frontend-next/ ./

# Build Next.js
RUN npm run build

# =============================================================================
# Runtime
# =============================================================================

FROM node:22-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends dumb-init curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY frontend-next/package*.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/node_modules ./node_modules

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:3000/ || exit 1

ENTRYPOINT ["dumb-init", "--"]
CMD ["npm", "start"]
