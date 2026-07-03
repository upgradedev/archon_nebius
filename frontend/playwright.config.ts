import { defineConfig, devices } from '@playwright/test'

// Browser E2E — the top of the testing pyramid. These tests render the REAL
// production bundle in a headless Chromium and assert UI *reachability*: that the
// components the app wires together are actually reachable through the browser
// (the class of bug an API-level test cannot see — e.g. a Review step ported into
// an orphaned component that the live modal never renders).
//
// Fully hermetic: no live backend, no models, no real auth. The suite mocks every
// `/api/**` call and Firebase auth via `page.route` + a seeded IndexedDB record
// (see e2e/fixtures.ts). Runs against `vite preview` of the production build so a
// build break is also caught here.
const PORT = 4173
const BASE_URL = `http://localhost:${PORT}`

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    // Build then serve the production bundle. `page.route` intercepts requests in
    // the browser before they leave, so the dev proxy target is irrelevant.
    command: `npm run build && npm run preview -- --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
})
