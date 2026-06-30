import type { NextConfig } from 'next';

const config: NextConfig = {
  // ─── Security headers ───
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(self), geolocation=()' },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: https:",
              "connect-src 'self' wss: https:",
              "frame-ancestors 'none'",
            ].join('; '),
          },
        ],
      },
    ];
  },

  // ─── Power Pack: enable experimental features ───
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },

  // ─── Compiler options ───
  typescript: {
    // Build fails on type errors — no exceptions
    ignoreBuildErrors: false,
  },
  eslint: {
    // Build fails on lint errors
    ignoreDuringBuilds: false,
  },

  // ─── Output: standalone for Docker ───
  output: 'standalone',

  // ─── Redirect www → non-www (or vice versa) ───
  async redirects() {
    return [];
  },
};

export default config;
