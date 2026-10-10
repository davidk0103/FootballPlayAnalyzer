import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5317'
const startServers = !process.env.E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: startServers
    ? [
        {
          command: 'uv run uvicorn app.main:app --host 127.0.0.1 --port 8317',
          cwd: '../backend',
          url: 'http://127.0.0.1:8317/health/ready',
          reuseExistingServer: true,
          timeout: 60_000,
        },
        {
          command: 'npm run dev',
          url: 'http://127.0.0.1:5317',
          reuseExistingServer: true,
          timeout: 60_000,
        },
      ]
    : undefined,
})
