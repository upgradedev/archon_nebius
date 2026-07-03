/**
 * Tests for the grounded executive-summary parsing + rendering.
 *
 * parseSummary splits the narrative body from the trailing "Sources:" line
 * that the narrator appends. We verify the with-Sources split, the graceful
 * no-Sources case (older reports), whitespace tolerance, and that the rendered
 * component surfaces the "Grounded sources" tags only when citations exist.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfigProvider, theme } from 'antd'
import React from 'react'
import ExecutiveSummary, { parseSummary } from '../components/ExecutiveSummary'

describe('parseSummary', () => {
  it('splits body from the trailing Sources line', () => {
    const raw =
      'Strong month: profit rose to €7,200.\n\nSources: payroll register 2026-01 · bank confirmation · validation R1'
    const { body, citations } = parseSummary(raw)
    expect(body).toBe('Strong month: profit rose to €7,200.')
    expect(citations).toEqual(['payroll register 2026-01', 'bank confirmation', 'validation R1'])
  })

  it('returns the whole string as body when no Sources line is present', () => {
    const raw = 'A plain older summary with no citations.'
    const { body, citations } = parseSummary(raw)
    expect(body).toBe(raw)
    expect(citations).toEqual([])
  })

  it('tolerates a single newline before the marker', () => {
    const raw = 'Body text.\nSources: IAS 19'
    const { body, citations } = parseSummary(raw)
    expect(body).toBe('Body text.')
    expect(citations).toEqual(['IAS 19'])
  })

  it('treats a Sources line with no citations as empty', () => {
    const raw = 'Body only.\n\nSources: '
    const { body, citations } = parseSummary(raw)
    expect(body).toBe('Body only.')
    expect(citations).toEqual([])
  })
})

function renderDark(ui: React.ReactElement) {
  return render(
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>{ui}</ConfigProvider>,
  )
}

describe('ExecutiveSummary component', () => {
  it('renders grounded-source tags when a Sources line exists', () => {
    renderDark(
      <ExecutiveSummary
        summary={'Good month.\n\nSources: bank confirmation · validation R1'}
        period="2026-01"
      />,
    )
    expect(screen.getByText('Good month.')).toBeInTheDocument()
    expect(screen.getByText('Grounded sources:')).toBeInTheDocument()
    expect(screen.getByText('bank confirmation')).toBeInTheDocument()
    expect(screen.getByText('validation R1')).toBeInTheDocument()
  })

  it('renders no sources section for an older report', () => {
    renderDark(<ExecutiveSummary summary={'Just a body, no sources.'} period="2026-01" />)
    expect(screen.getByText('Just a body, no sources.')).toBeInTheDocument()
    expect(screen.queryByText('Grounded sources:')).not.toBeInTheDocument()
  })
})
