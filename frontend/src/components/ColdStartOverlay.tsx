import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Spin } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { onColdStart } from '../api/coldStart'

// ── Nebius endpoint cold-start recovery ───────────────────────────────────────
// The Nebius CPU Serverless Endpoint scales to zero when idle and cold-starts in
// ~5 minutes. When a request fails with 502/503 during that window the api client
// emits a cold-start signal (see api/coldStart.ts). This overlay reacts by:
//   • NOT blanking anything — it renders as a fixed, non-blocking banner over the
//     current view, so the dashboard (or the sample fallback) stays visible;
//   • auto-polling /api/health on a fixed interval until the endpoint answers 2xx;
//   • showing honest progress ("warming up… (attempt N)") so the user waits
//     instead of hammering manual retries into another cold-start;
//   • resuming automatically on warm — it invalidates every query so the calls
//     that failed re-run against the now-warm endpoint;
//   • after a max window (~6 min) it stops auto-retrying and offers a single
//     manual "Retry now" — never a hard error.

const DEFAULT_POLL_MS = 20_000
const MAX_WINDOW_MS = 6 * 60_000

// The poll interval is overridable at runtime (window global) so tests can drive
// the recovery quickly without waiting real cold-start seconds.
function pollIntervalMs(): number {
  if (typeof window !== 'undefined') {
    const o = (window as unknown as { __ARCHON_COLDSTART_POLL_MS__?: number })
      .__ARCHON_COLDSTART_POLL_MS__
    if (typeof o === 'number' && o > 0) return o
  }
  return DEFAULT_POLL_MS
}

export default function ColdStartOverlay() {
  const queryClient = useQueryClient()
  const [active, setActive] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [gaveUp, setGaveUp] = useState(false)

  const timerRef = useRef<number | null>(null)
  const runningRef = useRef(false)
  const startedAtRef = useRef(0)

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const stop = useCallback(() => {
    clearTimer()
    runningRef.current = false
  }, [])

  const finishWarm = useCallback(() => {
    stop()
    setActive(false)
    setGaveUp(false)
    setAttempt(0)
    // Resume: re-run every query so the calls that failed during cold-start fetch
    // again against the now-warm endpoint. The UI recovers with no manual action.
    queryClient.invalidateQueries()
  }, [queryClient, stop])

  const tick = useCallback(async () => {
    setAttempt((a) => a + 1)
    let warm = false
    try {
      warm = await api.getHealth()
    } catch {
      /* network error while cold — treat as not-yet-warm */
    }
    if (warm) {
      finishWarm()
      return
    }
    if (Date.now() - startedAtRef.current > MAX_WINDOW_MS) {
      stop()
      setGaveUp(true)
      return
    }
    timerRef.current = window.setTimeout(() => void tick(), pollIntervalMs())
  }, [finishWarm, stop])

  const begin = useCallback(() => {
    if (runningRef.current) return // already recovering — ignore duplicate signals
    runningRef.current = true
    startedAtRef.current = Date.now()
    setGaveUp(false)
    setAttempt(0)
    // Confirm the endpoint is actually cold BEFORE surfacing the "starting up"
    // message. A 502/503 can come from a single failed request while the endpoint
    // is warm; showing the cold-start banner then is misleading. Only show it if
    // /api/health also fails — otherwise this was not a cold start.
    void (async () => {
      let warm = false
      try {
        warm = await api.getHealth()
      } catch {
        /* health call failed → treat as cold */
      }
      if (warm) {
        runningRef.current = false // not a cold start; stay silent
        return
      }
      setActive(true)
      void tick()
    })()
  }, [tick])

  useEffect(() => {
    const off = onColdStart(begin)
    return () => {
      off()
      stop()
    }
  }, [begin, stop])

  if (!active) return null

  return (
    <div
      style={{
        position: 'fixed',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 1200,
        padding: 16,
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
      }}
    >
      <div style={{ pointerEvents: 'auto', maxWidth: 560, width: '100%' }}>
        <Alert
          type={gaveUp ? 'warning' : 'info'}
          showIcon
          message="Nebius endpoint is starting up"
          description={
            gaveUp
              ? 'Still warming up — the serverless endpoint can take a few minutes on first use. Try again in a minute.'
              : `This can take ~5 minutes on first use. Retrying automatically… (attempt ${attempt})`
          }
          action={
            gaveUp ? (
              <Button size="small" onClick={begin}>
                Retry now
              </Button>
            ) : (
              <Spin />
            )
          }
        />
      </div>
    </div>
  )
}
