import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:8765',
    headless: true,
    viewport: { width: 1440, height: 900 },
  },
  webServer: {
    command: 'MAESTRO_LOCAL_DEV=true MAESTRO_DEMO_SEED=true MAESTRO_APP_DIR=. python backend/maestro_api/main.py',
    port: 8765,
    timeout: 30000,
    reuseExistingServer: true,
  },
});
