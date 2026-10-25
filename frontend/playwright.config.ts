import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  reporter: 'line',
  use: { baseURL: 'http://127.0.0.1:5175', channel: 'chrome' },
  webServer: {
    // Never reuse the developer's live app: its API override can bypass offline mocks.
    command: 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort',
    url: 'http://127.0.0.1:5175',
    env: { VITE_API_ROOT: 'http://localhost:8000/api' },
    reuseExistingServer: false,
  },
})
