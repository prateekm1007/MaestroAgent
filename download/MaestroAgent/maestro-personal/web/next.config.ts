import type { NextConfig } from "next";

// Railway/production: set BACKEND_URL to the backend's public URL
// Local dev: defaults to http://localhost:8766
const backendUrl = process.env.BACKEND_URL || `http://localhost:${process.env.MAESTRO_PORT || "8766"}`;

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
