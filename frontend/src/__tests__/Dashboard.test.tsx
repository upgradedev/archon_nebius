/**
 * Tests for the Dashboard page.
 *
 * Mocks React Query, API client, AuthContext, and Firebase so
 * the component renders in isolation with injected data.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, theme } from 'antd'

// Firebase mocks
vi.mock('../firebase', () => ({ auth: {}, googleProvider: {} }))
vi.mock('firebase/auth', () => ({
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn((_a, cb) => { cb(null); return () => {} }),
  GoogleAuthProvider: class {},
  getAuth: vi.fn(),
}))
vi.mock('firebase/app', () => ({
  initializeApp: vi.fn(),
  getApps: vi.fn(() => []),
  getApp: vi.fn(),
}))

// Auth context
const mockSignOut = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', email: 'test@archon.local', photoURL: null },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: mockSignOut,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// API client
const mockGetPeriods = vi.fn()
const mockGetReport = vi.fn()
const mockGetCompanyProfile = vi.fn()
vi.mock('../api/client', () => ({
  api: {
    getPeriods: mockGetPeriods,
    getReport: mockGetReport,
    getCompanyProfile: mockGetCompanyProfile,
    deletePeriod: vi.fn(),
    updateCompanyProfile: vi.fn(),
    upload: vi.fn(),
    submitJob: vi.fn(),
    analyze: vi.fn(),
    getJob: vi.fn(),
    getAnalysisJob: vi.fn(),
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

describe('Dashboard — empty state', () => {
  beforeEach(() => {
    mockGetPeriods.mockResolvedValue([])
    mockGetCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
    vi.clearAllMocks()
  })

  it('renders Archon header', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('Archon')).toBeTruthy())
  })

  it('shows empty state when no periods', async () => {
    mockGetPeriods.mockResolvedValue([])
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() =>
      expect(screen.getByText(/No period selected|upload documents/i)).toBeTruthy()
    )
  })

  it('shows Upload button', async () => {
    mockGetPeriods.mockResolvedValue([])
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => {
      const btns = screen.getAllByRole('button', { name: /upload/i })
      expect(btns.length).toBeGreaterThan(0)
    })
  })
})

describe('Dashboard — with periods', () => {
  const periods = [
    { period: '2025-01', hasReport: true, hasExtraction: true },
    { period: '2024-12', hasReport: false, hasExtraction: true },
  ]

  beforeEach(() => {
    mockGetPeriods.mockResolvedValue(periods)
    mockGetCompanyProfile.mockResolvedValue({ company_name: 'Acme', company_tax_id: '' })
    mockGetReport.mockRejectedValue(new Error('not found'))
    vi.clearAllMocks()
  })

  it('renders period tabs', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => {
      // Jan 2025 / Dec 2024 tabs should appear
      expect(screen.getByText(/Jan 2025/i)).toBeTruthy()
    })
  })
})

describe('Dashboard — upload modal', () => {
  beforeEach(() => {
    mockGetPeriods.mockResolvedValue([])
    mockGetCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
  })

  it('opens upload modal when Upload button clicked', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => screen.getAllByRole('button', { name: /upload/i }))
    const uploadBtns = screen.getAllByRole('button', { name: /upload/i })
    fireEvent.click(uploadBtns[0])
    await waitFor(() =>
      expect(screen.getByText(/Upload Documents|Select files|Reporting period/i)).toBeTruthy()
    )
  })
})

describe('Dashboard — sign out', () => {
  beforeEach(() => {
    mockGetPeriods.mockResolvedValue([])
    mockGetCompanyProfile.mockResolvedValue({ company_name: '', company_tax_id: '' })
  })

  it('calls signOut when logout button clicked', async () => {
    render(<Dashboard />, { wrapper: Wrapper })
    await waitFor(() => screen.getByRole('button', { name: /sign.?out|logout/i }))
    const logoutBtn = screen.getByRole('button', { name: /sign.?out|logout/i })
    fireEvent.click(logoutBtn)
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })
})
