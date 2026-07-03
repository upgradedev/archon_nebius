/**
 * Tests for the dashboard KPI tiles and their drill-down.
 *
 * The chart children are mocked so the test targets the tile interactivity
 * (click / keyboard / role gating + which detail view opens) rather than
 * Recharts internals, which need a real layout engine jsdom does not provide.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ConfigProvider, theme } from 'antd'
import React from 'react'

vi.mock('../components/PnLChart', () => ({
  default: () => <div data-testid="pnl-chart" />,
}))
vi.mock('../components/CashFlowChart', () => ({
  default: () => <div data-testid="cashflow-chart" />,
}))
vi.mock('../components/ExpenseBreakdown', () => ({
  default: () => <div data-testid="expense-chart" />,
}))

import MetricsCards from '../components/MetricsCards'
import { DEMO_REPORT } from '../demo/demoData'

const report = DEMO_REPORT.report

function wrap(node: React.ReactNode) {
  return render(
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>{node}</ConfigProvider>,
  )
}

describe('MetricsCards', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders all six KPI tiles', () => {
    wrap(<MetricsCards report={report} />)
    ;['Revenue', 'Net Profit', 'Gross Margin', 'Revenue Growth', 'Invoices', 'Collection Rate']
      .forEach(label => expect(screen.getByText(label)).toBeTruthy())
  })

  it('exposes exactly the four drillable tiles as buttons', () => {
    wrap(<MetricsCards report={report} />)
    // Revenue, Net Profit, Gross Margin, Collection Rate are drillable;
    // Revenue Growth and Invoices are deliberately inert.
    expect(screen.getAllByRole('button')).toHaveLength(4)
  })

  it('drills Revenue into the P&L view', async () => {
    wrap(<MetricsCards report={report} />)
    fireEvent.click(screen.getByText('Revenue'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeTruthy())
    expect(screen.getByTestId('pnl-chart')).toBeTruthy()
  })

  it('drills Gross Margin into the expense breakdown', async () => {
    wrap(<MetricsCards report={report} />)
    fireEvent.click(screen.getByText('Gross Margin'))
    await waitFor(() => expect(screen.getByTestId('expense-chart')).toBeTruthy())
  })

  it('drills Collection Rate into the cash-flow view', async () => {
    wrap(<MetricsCards report={report} />)
    fireEvent.click(screen.getByText('Collection Rate'))
    await waitFor(() => expect(screen.getByTestId('cashflow-chart')).toBeTruthy())
  })

  it('opens the drill-down via keyboard (Enter)', async () => {
    wrap(<MetricsCards report={report} />)
    const revenueTile = screen.getByLabelText('Revenue — open detail')
    fireEvent.keyDown(revenueTile, { key: 'Enter' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeTruthy())
  })

  it('does not make the Invoices tile clickable', () => {
    wrap(<MetricsCards report={report} />)
    expect(screen.queryByLabelText('Invoices — open detail')).toBeNull()
  })
})
