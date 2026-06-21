import React from 'react'

export default class ErrorBoundary extends React.Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '2rem', fontFamily: 'monospace' }}>
          <h2 style={{ color: '#c0392b' }}>The interface crashed</h2>
          <p>Copy the error below and send it to the developer:</p>
          <pre style={{
            background: '#fdf2f2', border: '1px solid #f5c6c6', borderRadius: 6,
            padding: '1rem', whiteSpace: 'pre-wrap', fontSize: '0.8rem', color: '#7b1f1f',
          }}>
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: '1rem', padding: '0.5rem 1rem', cursor: 'pointer' }}
          >
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
