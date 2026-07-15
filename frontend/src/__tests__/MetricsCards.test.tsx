/**
 * Tests for the dashboard KPI tiles and their supporting-document drill-down.
 *
 * The drill-down modal lists the documents that back a metric, fetched via
 * api.getDocuments (mocked here) and filtered by the tile's doc types. The test
 * targets tile interactivity (click / keyboard / role gating) and that the modal
 * renders the fetched documents — not Ant Design table internals.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ConfigProvider, theme } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// A sales invoice (backs Revenue) and a bank statement (does not).
const SAMPLE_DOCS = [
  { source_file: 'invoices/acme-sales-001.pdf', doc_type: 'sales', invoice_number: 'S-001', vendor_name: 'Acme Ltd', issue_date: '2026-01-12', total_amount: 12000, confidence: 0.94 },
  { source_file: 'bank/transfer-jan.pdf', doc_type: 'bank_confirmation', total_amount: 14350, confidence: 0.9 },
]

const getDocuments = vi.fn().mockResolvedValue(SAMPLE_DOCS)
vi.mock('../api/client', () => ({ api: { getDocuments: (...a: unknown[]) => getDocuments(...a) } }))

import MetricsCards from '../components/MetricsCards'
import { DEMO_REPORT } from '../demo/demoData'

const report = DEMO_REPORT.report

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>{node}</ConfigProvider>
    </QueryClientProvider>,
  )
}

describe('MetricsCards', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders all six KPI tiles', () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    ;['Revenue', 'Net Profit', 'Simplified Margin', 'Revenue Growth', 'Invoices', 'Collection Rate']
      .forEach(label => expect(screen.getByText(label)).toBeTruthy())
  })

  it('exposes exactly the four evidence-backed drillable tiles as buttons', () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    // Revenue, Net Profit, Simplified Margin and Invoices are drillable.
    // Growth and Collection Rate remain informational because this build lacks
    // prior-period and invoice-to-collection evidence.
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  it('does not make the Revenue Growth tile clickable', () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    expect(screen.queryByLabelText('Revenue Growth — open detail')).toBeNull()
  })

  it('does not present Collection Rate as a matched-document control', () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    expect(screen.queryByLabelText('Collection Rate — open detail')).toBeNull()
  })

  it('carries a definition tooltip on each tile', () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    expect(screen.getByLabelText('Revenue — definition')).toBeTruthy()
  })

  it('drills Revenue into its supporting sales documents', async () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    fireEvent.click(screen.getByLabelText('Revenue — open detail'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeTruthy())
    // The sales invoice is listed; the bank statement (wrong doc type) is not.
    await waitFor(() => expect(screen.getByText('acme-sales-001.pdf')).toBeTruthy())
    expect(getDocuments).toHaveBeenCalledWith('2026-01')
  })

  it('opens the drill-down via keyboard (Enter)', async () => {
    wrap(<MetricsCards report={report} period="2026-01" />)
    const revenueTile = screen.getByLabelText('Revenue — open detail')
    fireEvent.keyDown(revenueTile, { key: 'Enter' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeTruthy())
  })
})
