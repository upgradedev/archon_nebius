/**
 * Tests for the Dashboard page.
 *
 * vi.hoisted() is used for mock variables that are referenced inside vi.mock()
 * factories — those factories run before any top-level const declarations.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, theme } from 'antd'
import React from 'react'

// Hoist mock functions so they're available inside vi.mock() factories
const mocks = vi.hoisted(() => ({
  signOut: vi.fn(),
  getPeriods: vi.fn(),
  getReport: vi.fn(),
  getCompanyProfile: vi.fn(),
  deletePeriod: vi.fn(),
  updateCompanyProfile: vi.fn(),
  upload: vi.fn(),
  submitJob: vi.fn(),
  analyze: vi.fn(),
  getJob: vi.fn(),
  getAnalysisJob: vi.fn(),
}))

// Firebase mocks
vi.mock('../firebase', () => ({ auth: {}, googleProvider: {} }))
vi.mock('firebase/auth', () => ({
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn((_a: unknown, cb: (u: null) => void) => { cb(null); return () => {} }),
  GoogleAuthProvider: class {},
  getAuth: vi.fn(),
}))
vi.mock('firebase/app', () => ({
  initializeApp: vi.fn(),
  getApps: vi.fn(() => []),
  getApp: vi.fn(),
}))

// Auth context
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', email: 'test@archon.local', photoURL: null },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: mocks.signOut,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// API client
vi.mock('../api/client', () => ({
  api: {
    getPeriods: mocks.getPeriods,
    getReport: mocks.getReport,
    getCompanyProfile: mocks.getCompanyProfile,
    deletePeriod: mocks.deletePeriod,
    updateCompanyProfile: mocks.updateCompanyProfile,
    upload: mocks.upload,
    submitJob: mocks.submitJob,
    analyze: mocks.analyze,
    getJob: mocks.getJob,
    getAnalysisJob: mocks.getAnalysisJob,
  },
}))

import Dashboard from '../pages/Dashboard'

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </ConfigProvider>
  )
}

describe('Dashboard — signed-in empty store (sample-data fallback)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPeriods.mockResolvedValue([])
    mocks.getCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
  })

  it('renders Archon header', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('Archon')).toBeTruthy())
  })

  it('shows the sample-data fallback (banner + sample dashboard), not an empty state', async () => {
    // A signed-in user with an empty store falls back to the shared sample dataset
    // (with an honest banner) instead of a blank dashboard.
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() =>
      expect(screen.getByText(/Demo dataset — this is a shared sample/i)).toBeTruthy(),
    )
    // The sample dashboard renders (Ask Archon panel) — NOT the empty-state CTA.
    expect(screen.getByText('Ask Archon')).toBeTruthy()
    expect(screen.queryByText('No period selected')).toBeNull()
  })

  it('shows Upload button in header', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => {
      const btns = screen.getAllByRole('button', { name: /upload/i })
      expect(btns.length).toBeGreaterThan(0)
    })
  })
})

describe('Dashboard — with periods', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPeriods.mockResolvedValue([
      { period: '2025-01', hasReport: true, hasExtraction: true },
      { period: '2024-12', hasReport: false, hasExtraction: true },
    ])
    mocks.getCompanyProfile.mockResolvedValue({ company_name: 'Acme', company_tax_id: '' })
    mocks.getReport.mockRejectedValue(new Error('not found'))
  })

  it('renders Jan 2025 period tab', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText(/Jan 2025/i)).toBeTruthy())
  })

  it('renders Dec 2024 period tab', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText(/Dec 2024/i)).toBeTruthy())
  })
})

describe('Dashboard — upload modal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPeriods.mockResolvedValue([])
    mocks.getCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
  })

  it('opens upload modal when header Upload button is clicked', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => screen.getAllByRole('button', { name: /upload/i }))
    fireEvent.click(screen.getAllByRole('button', { name: /upload/i })[0])
    // Ant Design v5 Modal renders a portal with role="dialog" when open
    await waitFor(
      () => expect(screen.queryByRole('dialog')).toBeTruthy(),
      { timeout: 3000 }
    )
  })
})

describe('Dashboard — sign out', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPeriods.mockResolvedValue([])
    mocks.getCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
  })

  it('calls signOut when the sign-out button is clicked', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => screen.getByRole('button', { name: /sign.?out/i }))
    fireEvent.click(screen.getByRole('button', { name: /sign.?out/i }))
    expect(mocks.signOut).toHaveBeenCalledTimes(1)
  })
})
