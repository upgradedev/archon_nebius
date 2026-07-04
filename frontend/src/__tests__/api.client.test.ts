/**
 * Unit tests for src/api/client.ts
 *
 * Uses vi.hoisted() so mock objects are available inside vi.mock() factories,
 * which Vitest hoists to the top of the file before other variable declarations.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.hoisted() runs before everything else — safe to reference in vi.mock factories
const mockHttp = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}))

vi.mock('../firebase', () => ({
  auth: { currentUser: null },
}))

vi.mock('axios', async () => {
  const actual = await vi.importActual<{ default: typeof import('axios').default }>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockHttp),
    },
  }
})

// Import after mocks are registered
import { api } from '../api/client'

describe('api.getPeriods', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls GET /api/periods', async () => {
    mockHttp.get.mockResolvedValueOnce({ data: [] })
    const result = await api.getPeriods()
    expect(mockHttp.get).toHaveBeenCalledWith('/api/periods')
    expect(result).toEqual([])
  })

  it('returns period list from server', async () => {
    const periods = [{ period: '2025-01', hasReport: true, hasExtraction: true }]
    mockHttp.get.mockResolvedValueOnce({ data: periods })
    const result = await api.getPeriods()
    expect(result).toEqual(periods)
  })
})

describe('api.deletePeriod', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls DELETE /api/periods/{period}', async () => {
    mockHttp.delete.mockResolvedValueOnce({ data: { deleted: 3 } })
    await api.deletePeriod('2025-01')
    expect(mockHttp.delete).toHaveBeenCalledWith('/api/periods/2025-01')
  })
})

describe('api.getCompanyProfile', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls GET /api/company-profile', async () => {
    mockHttp.get.mockResolvedValueOnce({ data: { company_name: 'Acme', company_tax_id: '123' } })
    const result = await api.getCompanyProfile()
    expect(mockHttp.get).toHaveBeenCalledWith('/api/company-profile')
    expect(result.company_name).toBe('Acme')
  })
})

describe('api.updateCompanyProfile', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls PUT /api/company-profile with body', async () => {
    const profile = { company_name: 'Beta', company_tax_id: '999' }
    mockHttp.put.mockResolvedValueOnce({ data: profile })
    const result = await api.updateCompanyProfile(profile)
    expect(mockHttp.put).toHaveBeenCalledWith('/api/company-profile', profile)
    expect(result).toEqual(profile)
  })
})

describe('api.getReport', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls GET /api/reports/{period}', async () => {
    const report = { jobId: 'j1', report: {}, generatedAt: '2025-01-01T00:00:00Z' }
    mockHttp.get.mockResolvedValueOnce({ data: report })
    await api.getReport('2025-01')
    expect(mockHttp.get).toHaveBeenCalledWith('/api/reports/2025-01')
  })
})

describe('api.submitJob', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls POST /api/jobs with uploadId and period', async () => {
    const job = { id: 'j1', status: 'pending', period: '2025-01', documentsCount: 0, createdAt: '' }
    mockHttp.post.mockResolvedValueOnce({ data: job })
    const result = await api.submitJob('upload-abc', '2025-01')
    expect(mockHttp.post).toHaveBeenCalledWith('/api/jobs', { uploadId: 'upload-abc', period: '2025-01' })
    expect(result.id).toBe('j1')
  })
})

describe('api.analyze', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls POST /api/analyze with period', async () => {
    const job = { id: 'j2', status: 'pending', period: '2025-01', documentsCount: 0, createdAt: '' }
    mockHttp.post.mockResolvedValueOnce({ data: job })
    await api.analyze('2025-01')
    expect(mockHttp.post).toHaveBeenCalledWith('/api/analyze', { period: '2025-01' })
  })
})
