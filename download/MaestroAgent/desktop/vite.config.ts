import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // Tauri expects a fixed port; if not available, fall back.
  server: {
    port: 1420,
    strictPort: true,
  },
  // Tauri build: emit files where tauri.conf.json expects them.
  build: {
    outDir: "dist",
    target: "es2022",
    sourcemap: true,
  },
  // Don't clear the screen on reload — keeps Tauri CLI output visible.
  clearScreen: false,
});
