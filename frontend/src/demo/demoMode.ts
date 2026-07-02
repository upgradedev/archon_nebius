// Demo mode — a zero-backend, no-auth rendering of the REAL dashboard with a
// seeded sample report. Enabled by `?demo=1` (or `?demo=true`) in the URL.
//
// Why it exists: the public app gates the dashboard behind Google sign-in, so a
// CI runner (and the demo-video Playwright tour) only ever sees the login page.
// Demo mode lets the beat-aligned tour capture the ACTUAL dashboard components —
// P&L, the payroll-gap insight, and the R1–R4 validation ledger — rendered from
// synthetic fixtures with NO network calls and NO authenticated identity.
//
// Safety: when this returns true the api client short-circuits every read to the
// local fixture (no `/api` request is ever issued) and RequireAuth is bypassed.
// It only ever renders client-side synthetic data.
export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false
  const p = new URLSearchParams(window.location.search).get('demo')
  return p === '1' || p === 'true'
}

// The period the demo dashboard auto-selects.
export const DEMO_PERIOD = '2026-01'
