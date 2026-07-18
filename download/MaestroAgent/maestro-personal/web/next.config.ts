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
  // Proxy all /api/* requests to the Maestro backend.
  // - Local dev: http://localhost:8766
  // - Railway/prod: https://maestro-backend.up.railway.app
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
