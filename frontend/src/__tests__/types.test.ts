/**
 * Type-level smoke tests — verify the TypeScript interfaces compile and
 * can be constructed without errors. No runtime assertions needed; if these
 * imports fail the test fails.
 */
import { describe, it, expect } from 'vitest'
import type {
  PeriodInfo,
  CompanyProfile,
  ExtractedDoc,
  Job,
  FinancialReport,
  AnalysisResponse,
} from '../types/financial'

describe('type smoke tests', () => {
  it('PeriodInfo has required fields', () => {
    const p: PeriodInfo = { period: '2025-01', hasReport: true, hasExtraction: false }
    expect(p.period).toBe('2025-01')
    expect(p.hasReport).toBe(true)
  })

  it('CompanyProfile accepts empty strings', () => {
    const c: CompanyProfile = { company_name: '', company_tax_id: '' }
    expect(c).toBeTruthy()
  })

  it('ExtractedDoc optional fields default correctly', () => {
    const d: ExtractedDoc = { filename: 'invoice.pdf', doc_type: 'invoice' }
    expect(d.total_amount).toBeUndefined()
    expect(d.employee_count).toBeUndefined()
  })

  it('Job has all required fields', () => {
    const j: Job = {
      id: 'j1',
      status: 'pending',
      period: '2025-01',
      documentsCount: 3,
      createdAt: '2025-01-01T00:00:00Z',
    }
    expect(j.id).toBe('j1')
    expect(j.completedAt).toBeUndefined()
  })

  it('AnalysisResponse wraps FinancialReport', () => {
    const r: AnalysisResponse = {
      jobId: 'j2',
      report: {} as FinancialReport,
    }
    expect(r.jobId).toBe('j2')
  })
})
