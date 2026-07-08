// Cold-start signal bus.
//
// The Nebius CPU Serverless Endpoint scales to zero when idle and cold-starts in
// ~5 minutes. A request during that window times out at the Firebase BFF (~60s)
// and surfaces as a 502 (or a 503 from ADR-009 capacity handling). Rather than
// dumping the user to an error screen and letting them manually retry into a
// repeated cold-start loop, the axios response interceptor emits a cold-start
// signal here, and <ColdStartOverlay> (mounted on the dashboard) subscribes to it
// to drive a non-destructive, auto-retrying "warming up" experience.
//
// Tiny synchronous pub/sub — no React dependency so the api client can emit
// without importing component code.

type Listener = () => void

const listeners = new Set<Listener>()

export function onColdStart(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function emitColdStart(): void {
  for (const listener of listeners) {
    try {
      listener()
    } catch {
      /* a broken listener must never break the request pipeline */
    }
  }
}
