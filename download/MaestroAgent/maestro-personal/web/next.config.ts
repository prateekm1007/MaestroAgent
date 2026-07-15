import type { NextConfig } from "next";

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
};

export default nextConfig;
