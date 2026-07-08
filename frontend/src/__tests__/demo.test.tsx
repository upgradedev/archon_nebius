/**
 * Tests for demo-mode fixtures and the payroll-gap / R1–R4 dashboard panels
 * that the demo-video tour captures. Firebase is stubbed so the api client can
 * be imported without initializing a real app.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfigProvider, theme } from 'antd'
import React from 'react'
import PayrollGapCard from '../components/PayrollGapCard'
import ValidationLedger from '../components/ValidationLedger'
import { DEMO_REPORT, DEMO_PERIODS } from '../demo/demoData'

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

  it('carries the payroll-gap insight aligned with the narration (bank < true cost, +72%)', () => {
    const g = DEMO_REPORT.report.payrollGap!
    expect(g).toBeTruthy()
    expect(g.bankTransferNet).toBeLessThan(g.trueEmployerCost)
    // full understatement of true employer cost over the bank net transfer
    expect(Math.round(g.gapPct)).toBe(72)
  })

  it('carries R1–R4 all passing — R2/R4 now active (the keystone finding, fixed)', () => {
    const v = DEMO_REPORT.report.validations!
    expect(v.map(r => r.id)).toEqual(['R1', 'R2', 'R3', 'R4'])
    for (const id of ['R1', 'R2', 'R3', 'R4']) {
      expect(v.find(r => r.id === id)!.state).toBe('pass')
    }
  })
})

describe('PayrollGapCard', () => {
  it('renders both figures and the gap percentage', () => {
    wrap(<PayrollGapCard gap={DEMO_REPORT.report.payrollGap!} />)
    expect(screen.getByText('Bank transfer (net)')).toBeTruthy()
    expect(screen.getByText('True employer cost')).toBeTruthy()
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
