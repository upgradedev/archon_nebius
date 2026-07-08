import { test, expect } from '@playwright/test'
import type { Route } from '@playwright/test'
import { signIn, REPORT, COMPANY_PROFILE, TEST_PERIOD } from './fixtures'

// ── Nebius endpoint cold-start recovery ───────────────────────────────────────
// The signed-in real path must NOT strand a user on an error screen when the
// Nebius endpoint is cold-starting (502/503 at the BFF). This test drives the
// exact failure the user hit: a report load returns 502 while the endpoint warms
// up. It asserts the app (a) shows a non-destructive "warming up / retrying"
// state WITHOUT blanking the dashboard chrome, (b) auto-polls /api/health, and
// (c) resumes on its own once health returns 200 — with NO manual click.

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

test('cold start: non-blanking warming state, auto-retry health until warm, auto-resume', async ({
  page,
}) => {
  // Speed the backoff (vs the 20s production default) so the poll re-probes
  // promptly once we let the endpoint go warm.
  await page.addInitScript(() => {
    ;(window as unknown as { __ARCHON_COLDSTART_POLL_MS__?: number }).__ARCHON_COLDSTART_POLL_MS__ = 300
  })

  let reportCalls = 0
  let healthCalls = 0
  // The endpoint stays cold until the test has OBSERVED the warming state, then we
  // flip it warm — deterministic, no dependence on a transient timing window.
  let allowWarm = false

  // Catch-all FIRST (lowest priority) so nothing leaks to a real backend; the
  // specific routes below are registered later and therefore win.
  await page.route('**/api/**', (route) => json(route, {}))
  // Two periods so selecting one fires the Tabs onChange (a lone tab is
  // auto-active, so clicking it is a no-op). The first is active by default; the
  // test selects the second (TEST_PERIOD) to trigger its report fetch.
  await page.route('**/api/periods', (route) =>
    json(route, [
      { period: '2026-02', hasReport: true, hasExtraction: true },
      { period: TEST_PERIOD, hasReport: true, hasExtraction: true },
    ]),
  )
  await page.route('**/api/company-profile', (route) => json(route, COMPANY_PROFILE))

  // The report is COLD on the first load (502) and warm afterwards.
  await page.route('**/api/reports/**', (route) => {
    reportCalls += 1
    if (reportCalls === 1) return json(route, { error: 'cold' }, 502)
    return json(route, REPORT)
  })

  // Health: 502 (cold) until the test flips `allowWarm`, then 200 (warm).
  await page.route('**/api/health', (route) => {
    healthCalls += 1
    if (!allowWarm) return route.fulfill({ status: 502, body: 'cold' })
    return json(route, { status: 'ok' })
  })

  await signIn(page)

  // Select the period → triggers the report fetch, which returns 502 (cold).
  await page.getByRole('tab', { name: /Jan 2026/ }).click()

  // (a) A non-destructive "warming up / retrying" state appears — the calm
  // in-content notice AND the auto-retry overlay — NOT the destructive red error.
  await expect(page.getByText(/load automatically once it's warm/)).toBeVisible()
  await expect(page.getByText(/Retrying automatically/)).toBeVisible()
  await expect(page.getByText('Couldn’t load the report')).toHaveCount(0)
  await expect(page.getByText("Couldn't load the report")).toHaveCount(0)

  // Dashboard chrome is NOT blanked — the header + its Upload button remain.
  await expect(page.getByRole('banner').getByRole('button', { name: 'Upload' })).toBeVisible()

  // The endpoint really was probed while cold (auto-retry is running).
  expect(healthCalls).toBeGreaterThanOrEqual(1)

  // (c) Let the endpoint go warm. The app must resume ON ITS OWN — the overlay
  // clears and the report renders. No manual retry click anywhere in this test.
  allowWarm = true
  await expect(page.getByText(/Retrying automatically/)).toBeHidden({ timeout: 10_000 })
  await expect(page.getByRole('button', { name: 'Revenue — open detail' })).toBeVisible()
})
