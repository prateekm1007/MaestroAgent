FROM node:20-slim

WORKDIR /app

# Copy package files
COPY web/package.json web/package-lock.json ./

RUN npm ci --no-audit --no-fund

# Copy source
COPY web/ ./

# Build
RUN npm run build

# Expose port
EXPOSE 3000

ENV PORT=3000
ENV NODE_ENV=production

# Start
CMD ["npm", "run", "start"]
