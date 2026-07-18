FROM node:20-slim

WORKDIR /app

# Copy package files first (for Docker layer caching)
COPY package.json package-lock.json ./

RUN npm ci --no-audit --no-fund

# Copy all web source
COPY . .

# Build
RUN npm run build

# Railway injects PORT automatically — Next.js reads it via `next start -p $PORT`.
# Don't hardcode EXPOSE or ENV PORT — let Railway set it.
ENV NODE_ENV=production

# Start
CMD ["npm", "run", "start"]
