import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  reporter: 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  // Run against the user's existing local app when present. The backend is
  // intentionally external to this config so E2E tests exercise the real API.
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
