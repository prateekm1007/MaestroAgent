import type { NextConfig } from "next";

// Railway/production: BACKEND_URL env var (set in Railway dashboard).
// If not set at build time, hardcode the known Railway backend URL.
// Local dev: defaults to http://localhost:8766
const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "https://maestroagent-production.up.railway.app";

const nextConfig: NextConfig = {
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // Fix: Turbopack needs explicit root when nested in a monorepo
  turbopack: {
    root: __dirname,
  },
  // Session 10 fix (auditor F12): add security headers to the frontend.
  // The backend already has these headers; the frontend (Next.js) was missing them.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          {
            key: "Content-Security-Policy",
            value: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: https:; connect-src 'self' https://maestroagent-production.up.railway.app wss://maestroagent-production.up.railway.app; frame-ancestors 'none';",
          },
        ],
      },
    ];
  },
  // Proxy all /api/* requests to the Maestro backend.
  // - Local dev: http://localhost:8766
  // - Railway/prod: https://maestroagent-production.up.railway.app
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${backendUrl}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
