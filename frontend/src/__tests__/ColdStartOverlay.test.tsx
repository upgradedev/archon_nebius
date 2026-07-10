import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import ColdStartOverlay from '../components/ColdStartOverlay'
import { emitColdStart } from '../api/coldStart'

const mocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: {
    getHealth: mocks.getHealth,
  },
}))

describe('ColdStartOverlay', () => {
  let queryClient: QueryClient
  let invalidateSpy: any

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    // Speed up poll interval for testing
    if (typeof window !== 'undefined') {
      (window as any).__ARCHON_COLDSTART_POLL_MS__ = 10
    }
  })

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }

  it('is initially hidden', () => {
    const { container } = render(<ColdStartOverlay />, { wrapper: Wrapper })
    expect(container.firstChild).toBeNull()
  })

  it('renders alert and spins when cold start is emitted', async () => {
    mocks.getHealth.mockResolvedValue(false)
    render(<ColdStartOverlay />, { wrapper: Wrapper })

    emitColdStart()

    await waitFor(() => {
      expect(screen.getByText(/Nebius endpoint is starting up/i)).toBeTruthy()
      expect(screen.getByText(/attempt 1/i)).toBeTruthy()
    })
  })

  it('automatically resumes and calls invalidateQueries when health becomes warm', async () => {
    let callCount = 0
    mocks.getHealth.mockImplementation(async () => {
      callCount++
      return callCount > 1
    })

    const { container } = render(<ColdStartOverlay />, { wrapper: Wrapper })
    emitColdStart()

    // First wait for it to become active and visible
    await waitFor(() => {
      expect(screen.getByText(/Nebius endpoint is starting up/i)).toBeTruthy()
    })

    // Then wait for it to automatically hide once health probe returns true
    await waitFor(() => {
      expect(container.firstChild).toBeNull()
    })

    expect(invalidateSpy).toHaveBeenCalled()
  })
})
