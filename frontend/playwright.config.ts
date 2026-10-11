import { defineConfig, devices } from '@playwright/test';
declare const process: { env: Record<string, string | undefined> };

const e2ePort = process.env.REFUTELLA_E2E_PORT || '5173';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  reporter: 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://localhost:${e2ePort}`,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  // Run against the user's existing local app when present. The backend is
  // intentionally external to this config so E2E tests exercise the real API.
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${e2ePort}`,
    url: `http://localhost:${e2ePort}`,
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
