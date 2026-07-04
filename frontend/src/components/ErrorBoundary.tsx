import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Alert } from 'antd'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Class error boundary — the only React construct that can catch render-time
 * exceptions from children. Guards the dashboard so a single malformed report
 * field (e.g. a missing nested object handed to a Recharts chart) degrades to an
 * inline message instead of blanking the whole app.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console for diagnosis; no telemetry sink at demo scale.
    console.error('Dashboard render error:', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <Alert
            type="error"
            showIcon
            message="Something went wrong rendering this report"
            description="The report data could not be displayed. Try refreshing this period, or re-run the analysis."
            style={{ maxWidth: 600, margin: '60px auto' }}
          />
        )
      )
    }
    return this.props.children
  }
}
