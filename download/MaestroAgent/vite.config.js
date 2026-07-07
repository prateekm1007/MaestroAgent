import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  publicDir: 'static',
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'app.html'),
      },
      output: {
        manualChunks: {
          'core': [
            'static/js/utils.js',
            'static/js/csp-shim.js',
            'static/js/core.js',
            'static/js/swr_cache.js',
            'static/js/maestro.js',
          ],
          'home': [
            'static/js/home_core.js',
            'static/js/home_renderers.js',
          ],
          'surfaces': [
            'static/js/ask.js',
            'static/js/ask_v2.js',
            'static/js/today.js',
            'static/js/work.js',
            'static/js/learn.js',
          ],
        },
      },
    },
    chunkSizeWarningLimit: 200,
    minify: 'terser',
    terserOptions: {
      compress: { drop_console: false, drop_debugger: true },
    },
    sourcemap: true,
  },
  server: {
    port: 1420,
    proxy: {
      '/api': 'http://localhost:8765',
      '/ws': { target: 'ws://localhost:8765', ws: true },
      '/static': 'http://localhost:8765',
    },
  },
});
