import { test, expect } from './fixtures'
import type { Page } from '@playwright/test'

// ── UI-reachability browser E2E ───────────────────────────────────────────────
// These assert what an API-level test CANNOT: that the components the app wires
// together are actually reachable through the browser. The regression this guards
// against is exactly the one that shipped — a Review step ported into an orphaned
// Upload component that the live Dashboard modal never rendered. Selectors favour
// roles / text over brittle CSS.

// Small page-object over the shared upload flow that the Dashboard modal hosts.
class UploadFlow {
  constructor(private page: Page) {}

  // The upload modal is an antd Modal (role="dialog").
  dialog() {
    return this.page.getByRole('dialog')
  }

  async open() {
    // Header ("banner") Upload button — scoped to avoid the Empty-state
    // "Upload documents" button.
    await this.page.getByRole('banner').getByRole('button', { name: 'Upload' }).click()
    await expect(this.dialog()).toBeVisible()
  }

  async uploadFile() {
    // antd's Dragger renders a hidden <input type="file">; setInputFiles drives it
    // directly. The 2026-01 filename lets the client auto-detect the period.
    await this.dialog()
      .locator('input[type="file"]')
      .setInputFiles({
        name: '2026-01-payroll-register.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4\n% archon e2e synthetic doc\n'),
      })
    // The name shows in both the antd upload-list item and a blue Tag — either
    // proves the file was accepted into the flow.
    await expect(this.dialog().getByText('2026-01-payroll-register.pdf').first()).toBeVisible()
    await this.dialog().getByRole('button', { name: /Extract & Analyse/ }).click()
  }
}

test('a. Dashboard upload modal renders the shared 5-step flow incl. a Review step', async ({
  authedPage: page,
}) => {
  const flow = new UploadFlow(page)
  await flow.open()
  const dialog = flow.dialog()

  // The stepper must have all five steps, including "Review" — the step that was
  // orphaned in the divergent inline flow.
  await expect(dialog.locator('.ant-steps-item')).toHaveCount(5)
  // exact:true → case-sensitive full match, so "Upload documents" (step) is not
  // confused with the modal title "Upload Documents".
  await expect(dialog.getByText('Upload documents', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Extract data', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Review', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Analyse', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Ready', { exact: true })).toBeVisible()

  // It is the SHARED <UploadPage> that renders (its dragger), not a divergent
  // inline flow.
  await expect(dialog.getByText('Drop files here or click to browse')).toBeVisible()
})

test('b→d. Full flow: upload → Review guard → dashboard KPIs + drill-down + summary', async ({
  authedPage: page,
}) => {
  const flow = new UploadFlow(page)
  const dialog = flow.dialog()

  await test.step('b. Review step renders the doc table + entity-ownership guard + controls', async () => {
    await flow.open()
    await flow.uploadFile()

    // Extraction (mocked) completes → Review step.
    await expect(dialog.getByText('Review extracted documents')).toBeVisible()

    // Entity-ownership guard fires for the one non-matching document.
    await expect(
      dialog.getByText(/document.*may not belong to Reflective IKE/i),
    ).toBeVisible()

    // The extracted-document table lists the docs, including the flagged one.
    await expect(dialog.getByText('foreign-supplier-invoice.pdf')).toBeVisible()
    await expect(dialog.getByText('sales-invoice-001.pdf')).toBeVisible()

    // Include/exclude controls — one checkbox per row.
    await expect(dialog.getByRole('checkbox')).toHaveCount(3)

    // Confirm → run analysis.
    await dialog.getByRole('button', { name: /Confirm & Run Analysis/ }).click()
  })

  await test.step('c. Analysis completes → dashboard KPI tiles → drill-down modal with a doc table', async () => {
    // KPI tiles render (drillable tiles expose a button role + aria-label).
    const revenueTile = page.getByRole('button', { name: 'Revenue — open detail' })
    await expect(revenueTile).toBeVisible()
    await expect(page.getByRole('button', { name: 'Net Profit — open detail' })).toBeVisible()

    // Clicking a tile opens the drill-down modal with its supporting-document table.
    await revenueTile.click()
    const drill = page.getByRole('dialog')
    await expect(drill.getByText('Revenue — supporting documents')).toBeVisible()
    await expect(drill.getByText('sales-invoice-001.pdf')).toBeVisible()
    // Close the drill-down.
    await page.keyboard.press('Escape')
  })

  await test.step('d. Executive summary renders (with its grounded Sources tags)', async () => {
    await expect(page.getByText('Executive Summary')).toBeVisible()
    await expect(page.getByText(/Generated by Llama-3\.3-70B-Instruct/)).toBeVisible()
    // Grounded narrator (#93): the trailing "Sources:" line is parsed OUT of the
    // body and rendered as individual citation Tags under a "Grounded sources:"
    // label, plus a "N sources" count Tag in the header. Assert that rendering
    // (the body no longer shows the raw "Sources:" prefix — it is tokenised).
    await expect(page.getByText('Grounded sources:')).toBeVisible()
    await expect(page.getByText('3 sources')).toBeVisible()
    // bank-confirmation-jan.pdf appears ONLY in the summary citations (not in the
    // extracted-doc set), so it is an unambiguous proof of a rendered source Tag.
    await expect(page.getByText('bank-confirmation-jan.pdf', { exact: true })).toBeVisible()
  })
})
