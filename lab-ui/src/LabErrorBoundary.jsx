import { Component } from 'react'

export default class LabErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="lab-page" style={{ padding: '2rem', maxWidth: 560, margin: '0 auto' }}>
          <h1>JM Lab — load error</h1>
          <p className="lab-muted">Hard refresh (Ctrl+Shift+R) usually fixes this after a deploy.</p>
          <pre className="lab-error-box" style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem' }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <p>
            <a href="/lab/">Back to Lab home</a>
            {' · '}
            <a href="/lab/#suite">5-pair dashboard</a>
          </p>
        </div>
      )
    }
    return this.props.children
  }
}
