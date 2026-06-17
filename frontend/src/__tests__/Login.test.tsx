/**
 * Tests for the Login page.
 *
 * Mocks Firebase so signInWithPopup never fires.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'

// Mock Firebase modules used by Login / AuthContext
vi.mock('../firebase', () => ({
  auth: {},
  googleProvider: {},
}))
vi.mock('firebase/auth', () => ({
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn((_auth, cb) => { cb(null); return () => {} }),
  GoogleAuthProvider: class {},
  getAuth: vi.fn(),
  initializeApp: vi.fn(),
}))
vi.mock('firebase/app', () => ({
  initializeApp: vi.fn(),
  getApps: vi.fn(() => []),
  getApp: vi.fn(),
}))

const mockSignInWithGoogle = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false, signInWithGoogle: mockSignInWithGoogle, signOut: vi.fn() }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import Login from '../pages/Login'

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <MemoryRouter>{children}</MemoryRouter>
    </ConfigProvider>
  )
}

describe('Login page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders Archon branding', () => {
    render(<Login />, { wrapper: Wrapper })
    expect(screen.getByText(/Archon/i)).toBeTruthy()
  })

  it('renders a Google sign-in button', () => {
    render(<Login />, { wrapper: Wrapper })
    const btn = screen.getByRole('button', { name: /google|sign in|continue/i })
    expect(btn).toBeTruthy()
  })

  it('calls signInWithGoogle when button clicked', async () => {
    render(<Login />, { wrapper: Wrapper })
    const btn = screen.getByRole('button', { name: /google|sign in|continue/i })
    fireEvent.click(btn)
    expect(mockSignInWithGoogle).toHaveBeenCalledTimes(1)
  })
})
