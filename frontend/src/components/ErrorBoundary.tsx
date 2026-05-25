import { Component, ReactNode } from "react"

interface Props {
  children: ReactNode
  fallback?: ReactNode
  /** Optional short label shown in the fallback header — useful when wrapping individual panels. */
  scope?: string
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    if (typeof console !== "undefined" && console.error) {
      console.error("[ErrorBoundary] caught error", error, info?.componentStack)
    }
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }
    if (this.props.fallback) {
      return this.props.fallback
    }
    const message = this.state.error?.message || "Beklenmeyen bir hata oluştu."
    const scope = this.props.scope ? ` — ${this.props.scope}` : ""
    return (
      <div className="error-boundary">
        <div className="error-boundary-card">
          <div className="error-boundary-title">Bir şeyler yanlış gitti{scope}</div>
          <div className="error-boundary-body">{message}</div>
          <button
            type="button"
            className="primary-button"
            onClick={() => this.setState({ hasError: false, error: undefined })}
          >
            Tekrar dene
          </button>
        </div>
      </div>
    )
  }
}
