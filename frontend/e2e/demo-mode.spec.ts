import { test, expect, type Page, type Request } from '@playwright/test'

// ── Demo-mode browser E2E (the zero-backend judge journey) ────────────────────
// This drives the app EXACTLY as a judge does: `/?demo=1`, no auth, NO backend,
// NO api mocking. It is the safety net for the class of bug that shipped —
// features that silently fall through to the real backend (→ 401) or to a
// disabled query (→ empty dialog) because their api-client method had no
// demo-mode branch.
//
// It differs deliberately from upload-review-dashboard.spec.ts: that suite mocks
// every `/api/**` and a Firebase session to exercise the AUTHENTICATED path. Here
// there is no mock and no auth — instead a strict guard FAILS the test if ANY
// `/api/*` request is even attempted. So a future un-stubbed call is caught
// automatically, whether it 401s or not.

// Distinctive filename that must appear in each tile's drill-down (proves the
// dialog is populated, not empty). Sourced from DEMO_DOCUMENTS.
const TILE_DOC: Record<string, string> = {
  Revenue: 'sales-invoice-3001.pdf',
  'Net Profit': 'payroll-register-jan.pdf',
  'Gross Margin': 'payslip-employee-01.pdf',
  'Collection Rate': 'bank-confirmation-jan.pdf',
  Invoices: 'aws-cloud-invoice.pdf',
}

// Install the strict no-backend guard. Records every `/api/*` request and aborts
// it (so nothing leaks to a real backend). The test asserts the list is empty.
function installApiGuard(page: Page): string[] {
  const violations: string[] = []
  page.route('**/api/**', (route) => {
    const req: Request = route.request()
    violations.push(`${req.method()} ${new URL(req.url()).pathname}`)
    return route.abort()
  })
  return violations
}

test.describe('demo mode — full judge journey, zero backend', () => {
  test('1. dashboard renders the report, payroll gap (72% / 35%) and KPIs', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')

    // Payroll-gap card — the core insight, with both denominators.
    await expect(page.getByText('Bank transfer (net)', { exact: true })).toBeVisible()
    await expect(page.getByText('True employer cost', { exact: true })).toBeVisible()
    await expect(page.getByText('+72%')).toBeVisible()
    await expect(page.getByText('6 employees')).toBeVisible()

    // The ~35% employer social-security wedge is narrated in the executive summary.
    await expect(page.getByText(/~35% over the transfer/)).toBeVisible()

    // KPI tiles carry real figures (revenue = €96,400).
    await expect(page.getByText('€96,400').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Revenue — open detail' })).toBeVisible()

    // Validation ledger — the R1–R4 card renders with all four rules passing.
    await expect(page.getByText('Cross-document validation — R1 to R4')).toBeVisible()
    await expect(page.getByText('All four rules fire end-to-end', { exact: false })).toBeVisible()
    await expect(page.getByText('PASS', { exact: true })).toHaveCount(4)

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })

  test('2. every metric tile opens a populated drill-down dialog', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')
    await expect(page.getByRole('button', { name: 'Revenue — open detail' })).toBeVisible()

    for (const [label, filename] of Object.entries(TILE_DOC)) {
      await page.getByRole('button', { name: `${label} — open detail` }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog.getByText(`${label} — supporting documents`)).toBeVisible()
      // The dialog must be POPULATED — the distinctive supporting doc is listed,
      // NOT the empty-state text.
      await expect(dialog.getByText(filename)).toBeVisible()
      // Close before opening the next tile.
      await dialog.getByRole('button', { name: 'Close' }).click()
      await expect(dialog).toBeHidden()
    }

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })

  test('3. upload flow runs end-to-end client-side and lands on the report', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')

    // Open the Dashboard upload modal (header Upload button — scoped so it does
    // not collide with the empty-state button).
    await page.getByRole('banner').getByRole('button', { name: 'Upload' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByText('Drop files here or click to browse')).toBeVisible()

    // Demo mode must state plainly that the upload runs a SAMPLE set (the user's
    // own file is not processed) — so the seeded rows are never mistaken for it.
    await expect(modal.getByText('Demo mode — sample run')).toBeVisible()
    await expect(modal.getByText(/Your own file isn't processed/)).toBeVisible()

    // Choose a file (antd Dragger hides an <input type=file>).
    await modal.locator('input[type="file"]').setInputFiles({
      name: '2026-01-payroll-register.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\n% archon demo synthetic doc\n'),
    })
    await expect(modal.getByText('2026-01-payroll-register.pdf').first()).toBeVisible()

    // Submit → upload progress → extraction completes → Review step.
    await modal.getByRole('button', { name: /Extract & Analyse/ }).click()
    await expect(modal.getByText('Review extracted documents')).toBeVisible({ timeout: 20_000 })
    // The Review step labels the seeded rows as the sample dataset.
    await expect(modal.getByText('Sample dataset (demo mode)')).toBeVisible()
    await expect(modal.getByText(/not your uploaded file/)).toBeVisible()
    // Review table is populated from the seeded document set.
    await expect(modal.getByText('sales-invoice-3001.pdf')).toBeVisible()

    // Confirm → analysis completes → success → modal closes → report re-renders.
    await modal.getByRole('button', { name: /Confirm & Run Analysis/ }).click()
    await expect(modal.getByText(/Analysis complete/)).toBeVisible({ timeout: 20_000 })
    await expect(modal).toBeHidden({ timeout: 15_000 })

    // Back on the populated dashboard.
    await expect(page.getByText('+72%')).toBeVisible()

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })

  test('4. company settings save, then delete period — both work with no backend', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')
    await expect(page.getByText('+72%')).toBeVisible()

    // ── Settings: open drawer, edit, save ──
    await page.getByRole('button', { name: 'Company settings' }).click()
    const drawer = page.getByRole('dialog').filter({ hasText: 'Company Settings' })
    await expect(drawer.getByText('Company Settings')).toBeVisible()
    const nameInput = drawer.getByPlaceholder('Acme Ltd')
    await expect(nameInput).toHaveValue('Northwind Trading Ltd')
    await nameInput.fill('Northwind Trading Ltd (Demo)')
    await drawer.getByRole('button', { name: 'Save' }).click()
    // The success toast confirms the mutation resolved client-side (no 401).
    await expect(page.getByText('Profile saved')).toBeVisible()

    // ── Delete the period (runs last: it clears the active period) ──
    await page.getByRole('button', { name: 'Delete period' }).click()
    // Popconfirm → confirm.
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page.getByText(/deleted/)).toBeVisible()
    // Dashboard falls back to the empty state — cleanly, not an error.
    await expect(page.getByText('No period selected')).toBeVisible()

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })

  test('5. P&L chart tooltip is legible (dark surface, not white) on hover', async ({ page }) => {
    await page.goto('/?demo=1')
    // Scope to the P&L card so we hover the right chart.
    const pnlCard = page.locator('.ant-card', { hasText: 'Revenue vs Expenses vs Net Profit' })
    await expect(pnlCard).toBeVisible()

    // Hover a bar to activate the Recharts tooltip (force: hover over the SVG
    // <path> bar reliably fires the chart's mousemove handler).
    const bar = pnlCard.locator('.recharts-bar-rectangle').first()
    await expect(bar).toBeVisible()
    await bar.hover({ force: true })

    // The tooltip content box must render with the dark theme surface — NOT the
    // Recharts default white (which was illegible on the dark canvas).
    const tooltip = pnlCard.locator('.recharts-default-tooltip').first()
    await expect(tooltip).toBeVisible()
    const bg = await tooltip.evaluate((el) => getComputedStyle(el).backgroundColor)
    // #1f2937 → rgb(31, 41, 55). Assert it is exactly the themed colour and, as a
    // guard against any regression back to the default, explicitly not white.
    expect(bg).toBe('rgb(31, 41, 55)')
    expect(bg).not.toBe('rgb(255, 255, 255)')
  })

  test('6. executive summary sits near the top (above the payroll gap and charts)', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')

    const summaryCard = page.locator('.ant-card', { hasText: 'Executive Summary' })
    const payrollCard = page.locator('.ant-card', { hasText: 'bank net vs true employer cost' })
    const pnlCard = page.locator('.ant-card', { hasText: 'Revenue vs Expenses vs Net Profit' })
    await expect(summaryCard).toBeVisible()
    await expect(payrollCard).toBeVisible()
    // The LLM executive summary renders (its static model attribution line).
    await expect(page.getByText(/Generated by Llama-3\.3-70B-Instruct/)).toBeVisible()

    // Vertical order: summary is above the payroll-gap card and the P&L chart.
    const sBox = await summaryCard.boundingBox()
    const pBox = await payrollCard.boundingBox()
    const cBox = await pnlCard.boundingBox()
    if (!sBox || !pBox || !cBox) throw new Error('missing card bounding boxes')
    expect(sBox.y).toBeLessThan(pBox.y)
    expect(sBox.y).toBeLessThan(cBox.y)

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })

  test('7. Ask Archon — every suggested question returns a grounded answer', async ({ page }) => {
    const violations = installApiGuard(page)
    await page.goto('/?demo=1')

    const ask = page.locator('.ant-card', { hasText: 'Ask Archon' })
    await expect(ask).toBeVisible()
    const answer = ask.getByTestId('ask-answer')

    // Each chip → a short answer citing the exact figure from DEMO_REPORT.
    const cases: { q: string; expect: RegExp }[] = [
      { q: 'What was the net profit this period?', expect: /Net profit was €24,550 .* 25\.5% operating margin/ },
      { q: "What's the total employer cost?", expect: /true employer cost is €18,400 across 6 employees/ },
      { q: 'How much did the bank transfer understate the true payroll cost?', expect: /bank moved €10,700.*€18,400.*72% understatement.*€7,700 hidden/ },
      { q: 'Which vendors cost the most?', expect: /Amazon Web Services \(€7,420\).*Google Cloud \(€4,180\).*Metro Toll Systems \(€2,960\)/ },
      { q: 'Were there any validation issues?', expect: /All 4 cross-document checks passed \(R1–R4\)\. No validation issues/ },
      { q: 'How much cash did the business generate?', expect: /Net cash generated was €11,900 .*92\.4% collection rate/ },
    ]

    for (const c of cases) {
      await ask.getByRole('button', { name: c.q }).click()
      await expect(answer).toBeVisible()
      await expect(answer).toHaveText(c.expect)
    }

    expect(violations, `Unexpected backend calls: ${violations.join(', ')}`).toEqual([])
  })
})
