import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

// https://vitejs.dev/config/
// PWA-first: the app is installable in Chrome/Firefox/Brave via the
// browser's "Install" button. The service worker caches the app shell
// for offline use; API calls still require the backend to be reachable.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/icon-192.png", "icons/icon-512.png", "favicon.ico"],
      manifest: {
        name: "MaestroAgent",
        short_name: "Maestro",
        description:
          "The open-source, browser-first conductor for AI agents. Advanced loops, dynamic sub-agents, persistent memory, verifiable autonomy.",
        theme_color: "#8b5cf6",
        background_color: "#0a0a0f",
        display: "standalone",
        orientation: "landscape-primary",
        scope: "/",
        start_url: "/",
        categories: ["productivity", "developer", "ai"],
        icons: [
          {
            src: "icons/icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any maskable",
          },
          {
            src: "icons/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
        shortcuts: [
          {
            name: "New Run",
            short_name: "Run",
            description: "Start a new agent workflow",
            url: "/?action=new-run",
          },
          {
            name: "Templates",
            short_name: "Templates",
            description: "Browse workflow templates",
            url: "/?view=templates",
          },
        ],
      },
      workbox: {
        // Cache the app shell aggressively; never cache API responses
        // (they must always be fresh from the backend).
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        globIgnores: ["**/api/**"],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        navigateFallback: "index.html",
        runtimeCaching: [
          {
            // Cache static assets for 30 days.
            urlPattern: ({ url }) => url.origin === self.location.origin,
            handler: "CacheFirst",
            options: {
              cacheName: "maestro-shell",
              expiration: { maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
        ],
      },
      devOptions: {
        // Enable SW in dev for testing installability.
        enabled: true,
        type: "module",
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 1420,
    host: true, // bind to 0.0.0.0 for Docker
    strictPort: false,
    // Proxy API + WS to the backend in dev so the browser sees same-origin.
    proxy: {
      "/api": {
        target: "http://localhost:8765",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8765",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    target: "es2022",
    sourcemap: true,
    chunkSizeWarningLimit: 1500,
  },
  // Tauri build emits to dist/ which the backend can serve statically
  // in production (single-container self-host).
  clearScreen: false,
});
