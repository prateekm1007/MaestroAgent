import type { NextConfig } from "next";

const maestroPort = process.env.MAESTRO_PORT || "8766";

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
  // Proxy all /api/* requests to the Maestro Personal backend on :8766.
  // This means the Next.js dev server (:3000) handles the UI, and all
  // API calls are forwarded to the FastAPI backend. You only need to
  // visit http://localhost:3000 — no need to visit :8766 directly.
  //
  // The XTransformPort query param in maestro-api.ts is still added for
  // backward compat, but the rewrite makes it unnecessary — Next.js
  // proxies the request to the backend directly.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${maestroPort}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `http://localhost:${maestroPort}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
