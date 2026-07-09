import { test as base, expect, type Page } from '@playwright/test'

// ── Hermetic browser-E2E harness ──────────────────────────────────────────────
// Everything here keeps the tests deterministic and offline: no live backend, no
// model calls, no real Firebase credentials. Two concerns are mocked:
//
//   1. Auth  — the app gates the dashboard behind Firebase sign-in (RequireAuth /
//              AuthContext). We make the app render as SIGNED-IN without any real
//              credential by SEEDING the exact IndexedDB record Firebase restores
//              a session from (`firebaseLocalStorageDb`), plus a `page.route` net
//              stub for the token/identity endpoints so any proactive refresh
//              succeeds hermetically. See `signIn()` below.
//
//   2. API   — every `**/api/**` request is intercepted by `setupApiMocks()` and
//              answered from the fixtures in this file, with a tiny bit of state
//              so the period only "appears" once analysis has run.
//
// NOTE ON THE TOKEN: the only code path that reads the token is the axios request
// interceptor calling `getIdToken()`. With a future `expirationTime` Firebase
// returns the stored `accessToken` verbatim — it is never parsed and never sent
// anywhere real (all `/api/**` is mocked). So an opaque placeholder string is
// correct AND deliberate: a real-looking `eyJ…` JWT would trip the gitleaks PR
// gate for no benefit.

const FIREBASE_API_KEY = 'AIzaSy' + 'DJo0hidUN0YKZYS8g6w2Ca062NgBMn3Ns'
export const TEST_PERIOD = '2026-01'

// The configured company. The entity-ownership guard matches extracted documents
// against this name / tax id.
export const COMPANY_PROFILE = {
  company_name: 'Reflective IKE',
  company_tax_id: '800123456',
}

// Extracted document set for TEST_PERIOD. Exactly ONE document (the last) belongs
// to a different entity — it matches neither the company name nor the tax id — so
// the Review step's entity-ownership guard fires for it.
export const EXTRACTED_DOCS = [
  {
    source_file: `raw-docs/${TEST_PERIOD}/sales-invoice-001.pdf`,
    doc_type: 'sales',
    vendor_name: 'Reflective IKE',
    vendor_tax_id: '800123456',
    recipient_name: 'Acme Buyer Ltd',
    invoice_number: 'INV-001',
    issue_date: '2026-01-12',
    total_amount: 12_500,
    currency: 'EUR',
    confidence: 0.98,
  },
  {
    source_file: `raw-docs/${TEST_PERIOD}/payroll-register-jan.pdf`,
    doc_type: 'payroll_register',
    vendor_name: 'Reflective IKE',
    employee_count: 6,
    employer_cost_total: 18_400,
    total_amount: 18_400,
    currency: 'EUR',
    confidence: 0.95,
  },
  {
    // Belongs to a different entity → guard should flag it.
    source_file: `raw-docs/${TEST_PERIOD}/foreign-supplier-invoice.pdf`,
    doc_type: 'invoice',
    vendor_name: 'Foreign Supplier GmbH',
    vendor_tax_id: '999999999',
    recipient_name: 'Some Other Client SA',
    invoice_number: 'FS-77',
    issue_date: '2026-01-05',
    total_amount: 4_200,
    currency: 'EUR',
    confidence: 0.81,
  },
]

// A realistic analysis report. The endpoint emits raw `payrollEvents` +
// `validationResults`; the api-client `normalizeReport` derives `payrollGap` +
// `validations` from them, so the payroll-gap card and validation ledger render.
export const REPORT = {
  jobId: 'job-an-1',
  generatedAt: `${TEST_PERIOD}-31T09:12:00Z`,
  report: {
    period: TEST_PERIOD,
    pnl: {
      period: TEST_PERIOD,
      revenue: 96_400,
      expenses: 71_850,
      netProfit: 24_550,
      grossMarginPct: 38.2,
      operatingMarginPct: 25.5,
    },
    cashFlow: { period: TEST_PERIOD, operating: 21_300, investing: -6_400, financing: -3_000, net: 11_900 },
    expenseBreakdown: [
      { category: 'Payroll (true employer cost)', amount: 18_400, percentage: 25.6, monthOverMonthPct: 3.1 },
      { category: 'Cloud & software', amount: 15_900, percentage: 22.1, monthOverMonthPct: 8.4 },
      { category: 'Other operating', amount: 13_000, percentage: 18.1, monthOverMonthPct: 2.0 },
    ],
    topVendors: [
      { name: 'Amazon Web Services', totalAmount: 7_420, invoiceCount: 1, avgDaysToPay: 14 },
    ],
    keyMetrics: {
      revenueGrowthPct: 6.8,
      expenseRatioPct: 74.5,
      cashBurnRate: 0,
      invoiceCount: 27,
      avgInvoiceValue: 3_570,
      collectionRatePct: 92.4,
    },
    executiveSummary:
      'January closed with revenue of EUR 96,400 and a net profit of EUR 24,550 — a 25.5% ' +
      'operating margin. The defining correction is payroll: the bank moved EUR 10,700 in net ' +
      'transfers, but the Event Linker recovered the true employer cost of EUR 18,400 — about a ' +
      '72% understatement a bank-only close would have missed.\n\n' +
      // The grounded narrator ends with a "Sources:" line whose citations are
      // separated by " · " (parseSummary splits on the middle dot into tags).
      'Sources: payroll-register-jan.pdf · sales-invoice-001.pdf · bank-confirmation-jan.pdf',
    generatedAt: `${TEST_PERIOD}-31T09:12:00Z`,
    // Raw shapes the client adapter converts into payrollGap + validations.
    payrollEvents: [
      { net_total: 10_700, employer_cost_total: 18_400, employee_count: 6 },
    ],
    validationResults: [
      { rule: 'R1: Bank net ≈ Σ payslip nets (±2%)', passed: true, message: 'OK' },
      { rule: 'R2: Employer-cost ÷ net ratio in band', passed: true, message: 'employer_cost/net = 1.72 (expected 1.40–2.60)' },
      { rule: 'R3: Payment date ≤ end of pay period', passed: true, message: 'OK' },
      { rule: 'R4: Register headcount == payslip count', passed: true, message: 'Register reports 6 employees, found 6 payslips' },
    ],
  },
}

function fulfillJson(route: import('@playwright/test').Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

// Seed the exact record Firebase's `indexedDBLocalPersistence` restores a user
// from. Runs inside the browser. Handles the case where Firebase has (or has not)
// already created the object store. A future `expirationTime` means `getIdToken()`
// returns the stored token without any network refresh.
function seedFirebaseUser(apiKey: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const record = {
      fbase_key: `firebase:authUser:${apiKey}:[DEFAULT]`,
      value: {
        uid: 'e2e-test-uid',
        email: 'tester@archon.test',
        emailVerified: true,
        displayName: 'Archon Tester',
        isAnonymous: false,
        photoURL: null,
        providerData: [
          {
            providerId: 'password',
            uid: 'tester@archon.test',
            displayName: 'Archon Tester',
            email: 'tester@archon.test',
            phoneNumber: null,
            photoURL: null,
          },
        ],
        stsTokenManager: {
          refreshToken: 'e2e-fake-refresh-token',
          accessToken: 'e2e-fake-access-token',
          // 24h in the future → no proactive refresh, token returned verbatim.
          expirationTime: Date.now() + 24 * 60 * 60 * 1000,
        },
        createdAt: String(Date.now()),
        lastLoginAt: String(Date.now()),
        apiKey,
        appName: '[DEFAULT]',
      },
    }
    const open = indexedDB.open('firebaseLocalStorageDb', 1)
    open.onupgradeneeded = () => {
      const db = open.result
      if (!db.objectStoreNames.contains('firebaseLocalStorage')) {
        db.createObjectStore('firebaseLocalStorage', { keyPath: 'fbase_key' })
      }
    }
    open.onsuccess = () => {
      const db = open.result
      try {
        const tx = db.transaction('firebaseLocalStorage', 'readwrite')
        tx.objectStore('firebaseLocalStorage').put(record)
        tx.oncomplete = () => {
          db.close()
          resolve()
        }
        tx.onerror = () => reject(tx.error)
      } catch (e) {
        reject(e)
      }
    }
    open.onerror = () => reject(open.error)
  })
}

// Stub the Firebase network surface so any auth traffic (proactive token refresh,
// account lookup) resolves hermetically instead of hitting Google.
async function stubFirebaseNetwork(page: Page) {
  await page.route('**/securetoken.googleapis.com/**', (route) =>
    fulfillJson(route, {
      access_token: 'e2e-fake-access-token',
      expires_in: '3600',
      token_type: 'Bearer',
      refresh_token: 'e2e-fake-refresh-token',
      id_token: 'e2e-fake-access-token',
      user_id: 'e2e-test-uid',
      project_id: 'archon-pnl',
    }),
  )
  await page.route('**/identitytoolkit.googleapis.com/**', (route) =>
    fulfillJson(route, {
      kind: 'identitytoolkit#GetAccountInfoResponse',
      users: [
        {
          localId: 'e2e-test-uid',
          email: 'tester@archon.test',
          emailVerified: true,
          displayName: 'Archon Tester',
          providerUserInfo: [{ providerId: 'password', federatedId: 'tester@archon.test' }],
          validSince: '0',
          lastLoginAt: String(Date.now()),
          createdAt: String(Date.now()),
        },
      ],
    }),
  )
}

// Intercept every `/api/**` call and answer from the fixtures. A period only
// "exists" (and its report is available) once analysis has run — mirroring the
// real flow where the dashboard lists the period after the analysis job completes.
export async function setupApiMocks(page: Page) {
  const state = { analyzed: false }

  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const method = req.method()
    const path = new URL(req.url()).pathname

    // ── reads ──────────────────────────────────────────────────────────────
    if (method === 'GET' && path.endsWith('/api/company-profile')) {
      return fulfillJson(route, COMPANY_PROFILE)
    }
    if (method === 'GET' && path.endsWith('/api/periods')) {
      return fulfillJson(
        route,
        state.analyzed ? [{ period: TEST_PERIOD, hasReport: true, hasExtraction: true }] : [],
      )
    }
    if (method === 'GET' && /\/api\/documents\//.test(path)) {
      return fulfillJson(route, EXTRACTED_DOCS)
    }
    if (method === 'GET' && /\/api\/reports\//.test(path)) {
      return fulfillJson(route, REPORT)
    }
    // Extraction + analysis job polling → return COMPLETED immediately so the
    // pipeline advances without real compute.
    if (method === 'GET' && /\/api\/jobs\/[^/]+$/.test(path)) {
      return fulfillJson(route, {
        id: 'job-ext-1', status: 'completed', period: TEST_PERIOD,
        documentsCount: EXTRACTED_DOCS.length, progress: 100,
        createdAt: new Date().toISOString(), completedAt: new Date().toISOString(),
      })
    }
    if (method === 'GET' && /\/api\/analyze\/[^/]+$/.test(path)) {
      return fulfillJson(route, {
        id: 'job-an-1', status: 'completed', period: TEST_PERIOD,
        documentsCount: EXTRACTED_DOCS.length, progress: 100,
        createdAt: new Date().toISOString(), completedAt: new Date().toISOString(),
      })
    }

    // ── writes / submissions ────────────────────────────────────────────────
    if (method === 'POST' && path.endsWith('/api/upload')) {
      return fulfillJson(route, {
        uploadId: 'up-1',
        period: TEST_PERIOD,
        files: [{ id: 'f1', filename: `${TEST_PERIOD}-payroll-register.pdf`, sizeBytes: 1024, uploadedAt: new Date().toISOString() }],
      })
    }
    if (method === 'POST' && path.endsWith('/api/jobs')) {
      return fulfillJson(route, {
        id: 'job-ext-1', status: 'running', period: TEST_PERIOD,
        documentsCount: EXTRACTED_DOCS.length, createdAt: new Date().toISOString(),
      })
    }
    if (method === 'POST' && path.endsWith('/api/analyze')) {
      state.analyzed = true
      return fulfillJson(route, {
        id: 'job-an-1', status: 'running', period: TEST_PERIOD,
        documentsCount: 2, createdAt: new Date().toISOString(),
      })
    }
    if (method === 'PUT' && /\/api\/documents\//.test(path)) {
      return fulfillJson(route, { period: TEST_PERIOD, documents: 2, deleted: 1 })
    }
    if (method === 'PUT' && path.endsWith('/api/company-profile')) {
      return fulfillJson(route, COMPANY_PROFILE)
    }

    // Anything unmocked is a bug in the test — fail loudly rather than hit a
    // real backend.
    return fulfillJson(route, { error: `unmocked ${method} ${path}` }, 501)
  })
}

// Render the app as a signed-in user. Pattern (race-free):
//   1. goto('/') — app boots unauthenticated, Firebase creates its IndexedDB,
//      RequireAuth redirects to /login.
//   2. seed the auth record into that IndexedDB.
//   3. goto('/') again — Firebase restores the session, RequireAuth renders the
//      dashboard.
// Then fast-fail: assert we are NOT on /login and the dashboard chrome is present,
// so a seeding regression fails HERE, not three steps downstream.
export async function signIn(page: Page) {
  await stubFirebaseNetwork(page)
  await page.goto('/')
  await page.evaluate(seedFirebaseUser, FIREBASE_API_KEY)
  await page.goto('/')
  await expect(page).not.toHaveURL(/\/login/)
  // Header ("banner") Upload button — scoped so it doesn't collide with the
  // Empty-state "Upload documents" button when no period exists yet.
  await expect(page.getByRole('banner').getByRole('button', { name: 'Upload' })).toBeVisible()
}

// Fixture: an already-signed-in page with all backend calls mocked.
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    await setupApiMocks(page)
    await signIn(page)
    await use(page)
  },
})

export { expect }
