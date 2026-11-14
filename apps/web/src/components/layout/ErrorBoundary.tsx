import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  error: Error | null
}

/**
 * 页面级错误边界：某个页面渲染失败时保留导航与登录态，避免整站白屏。
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('Page render failed', error, info)
  }

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div className="ttc-page">
          <div className="ttc-error-panel">
            <div>
              <strong>页面渲染失败</strong>
              <span>{this.state.error.message}</span>
            </div>
            <button
              type="button"
              className="ttc-btn ttc-btn-secondary ttc-btn-sm"
              onClick={() => this.setState({ error: null })}
            >
              重试渲染
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
