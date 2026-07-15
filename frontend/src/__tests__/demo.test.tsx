/**
 * Tests for demo-mode fixtures and the payroll-gap / R1–R4 dashboard panels
 * that the demo-video tour captures. Firebase is stubbed so the api client can
 * be imported without initializing a real app.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConfigProvider, theme } from 'antd'
import React from 'react'
import PayrollGapCard from '../components/PayrollGapCard'
import ValidationLedger from '../components/ValidationLedger'
import AskPanel from '../components/AskPanel'
import { DEMO_DOCUMENTS, DEMO_REPORT, DEMO_PERIODS } from '../demo/demoData'

function wrap(node: React.ReactNode) {
  return render(
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>{node}</ConfigProvider>,
  )
}

describe('demo fixtures', () => {
  it('seeds one period with a ready report', () => {
    expect(DEMO_PERIODS).toHaveLength(1)
    expect(DEMO_PERIODS[0].hasReport).toBe(true)
  })

  it('compares bank-confirmed net wages with registered employer cost (+72%)', () => {
    const g = DEMO_REPORT.report.payrollGap!
    expect(g).toBeTruthy()
    expect(g.bankTransferNet).toBeLessThan(g.trueEmployerCost)
    // Registered employer cost is ~72% above bank-confirmed net wages.
    expect(Math.round(g.gapPct)).toBe(72)
  })

  it('carries R1–R4 all passing — R2/R4 now active (the keystone finding, fixed)', () => {
    const v = DEMO_REPORT.report.validations!
    expect(v.map(r => r.id)).toEqual(['R1', 'R2', 'R3', 'R4'])
    for (const id of ['R1', 'R2', 'R3', 'R4']) {
      expect(v.find(r => r.id === id)!.state).toBe('pass')
    }
  })

  it('reproduces the seeded P&L, cash flow, and R1-R4 outcomes from its documents', () => {
    const amount = (d: (typeof DEMO_DOCUMENTS)[number]) => d.total_amount ?? 0
    const sales = DEMO_DOCUMENTS.filter((d) => d.doc_type === 'sales')
    const invoices = DEMO_DOCUMENTS.filter((d) => d.doc_type === 'invoice' || d.doc_type === 'expense')
    const register = DEMO_DOCUMENTS.find((d) => d.doc_type === 'payroll_register')!
    const bank = DEMO_DOCUMENTS.find((d) => d.doc_type === 'bank_confirmation')!
    const payslips = DEMO_DOCUMENTS.filter((d) => d.doc_type === 'payslip')

    const salesTotal = sales.reduce((sum, d) => sum + amount(d), 0)
    const invoiceExpenseTotal = invoices.reduce((sum, d) => sum + amount(d), 0)
    const payslipTotal = payslips.reduce((sum, d) => sum + amount(d), 0)
    const employerCost = register.employer_cost_total ?? amount(register)

    expect(salesTotal).toBe(DEMO_REPORT.report.pnl.revenue)
    expect(invoiceExpenseTotal + employerCost).toBe(DEMO_REPORT.report.pnl.expenses)
    expect(DEMO_REPORT.report.pnl.netProfit).toBe(salesTotal - invoiceExpenseTotal - employerCost)
    expect(DEMO_REPORT.report.expenseBreakdown.reduce((sum, row) => sum + row.amount, 0))
      .toBe(DEMO_REPORT.report.pnl.expenses)
    expect(salesTotal - invoiceExpenseTotal - amount(bank)).toBe(DEMO_REPORT.report.cashFlow.operating)
    expect(DEMO_REPORT.report.cashFlow).toMatchObject({ investing: 0, financing: 0, net: 32_250 })

    expect(payslips).toHaveLength(register.employee_count)
    expect(payslipTotal).toBe(amount(bank))
    expect(register.net_pay_total).toBe(amount(bank))
    expect(employerCost / register.net_pay_total!).toBeGreaterThanOrEqual(1.4)
    expect(employerCost / register.net_pay_total!).toBeLessThanOrEqual(2.6)
    expect(bank.issue_date! <= `${DEMO_REPORT.report.period}-31`).toBe(true)

    for (const vendor of DEMO_REPORT.report.topVendors) {
      const documentTotal = DEMO_DOCUMENTS
        .filter((d) => d.vendor_name === vendor.name)
        .reduce((sum, d) => sum + amount(d), 0)
      expect(documentTotal).toBe(vendor.totalAmount)
    }

    expect(DEMO_REPORT.report.keyMetrics.revenueGrowthPct).toBeNull()
    expect(DEMO_REPORT.report.keyMetrics.collectionRatePct).toBeNull()
  })
})

describe('PayrollGapCard', () => {
  it('renders both figures and the gap percentage', () => {
    wrap(<PayrollGapCard gap={DEMO_REPORT.report.payrollGap!} />)
    expect(screen.getByText('Bank transfer (net)')).toBeTruthy()
    expect(screen.getByText('Registered employer cost')).toBeTruthy()
    expect(screen.getByText(/\+72%/)).toBeTruthy()
  })
})

describe('ValidationLedger', () => {
  it('renders all four rules as PASS (R2/R4 now active)', () => {
    wrap(<ValidationLedger rules={DEMO_REPORT.report.validations!} />)
    expect(screen.getAllByText('PASS')).toHaveLength(4)
    expect(screen.queryByText('SKIPPED')).toBeNull()
  })
})

describe('AskPanel', () => {
  it('renders a suggested-question chip for each answerable question', () => {
    wrap(<AskPanel report={DEMO_REPORT.report} />)
    // All six questions are answerable from DEMO_REPORT.
    expect(screen.getByRole('button', { name: 'What was the net profit this period?' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'What employer cost does the payroll register report?' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'How do bank-confirmed net wages compare with registered employer cost?' })).toBeTruthy()
  })

  it('answers each question with the exact figure grounded in the report (no LLM, no 28%)', () => {
    const { getByRole, getByTestId } = wrap(<AskPanel report={DEMO_REPORT.report} />)

    fireEvent.click(getByRole('button', { name: 'What employer cost does the payroll register report?' }))
    expect(getByTestId('ask-answer').textContent).toContain('€18,400')

    fireEvent.click(getByRole('button', { name: 'How do bank-confirmed net wages compare with registered employer cost?' }))
    const gapText = getByTestId('ask-answer').textContent ?? ''
    expect(gapText).toContain('€10,700')
    expect(gapText).toContain('72%')
    expect(gapText).toContain('does not verify separate tax or social-insurance remittance')
    expect(gapText).not.toContain('28%')
  })
})
