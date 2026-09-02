import { useState } from 'react'
import { api } from './api'

const BIAS_CLASS = {
  BUY: 'buy',
  SELL: 'sell',
  WAIT: 'sell',
  NEUTRAL: '',
}

export default function ClaudeChartPanel({ interval = '5', symbol = 'XAUUSD' }) {
  const [status, setStatus] = useState('idle') // idle | loading | ready | error | off
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState('')
  const [configured, setConfigured] = useState(null)

  async function checkStatus() {
    try {
      const st = await api.claudeStatus()
      setConfigured(st.configured && st.enabled)
      return st.configured && st.enabled
    } catch {
      setConfigured(false)
      return false
    }
  }

  async function analyze() {
    setStatus('loading')
    setError('')
    try {
      const ok = configured ?? (await checkStatus())
      if (!ok) {
        setStatus('off')
        setError('Set JM_ANTHROPIC_API_KEY on the server to enable Claude.')
        return
      }
      const res = await api.claudeChartAnalysis({ interval, symbol, limit: 400 })
      const row = res.analysis
      if (!row?.ok) throw new Error(row?.error || 'Claude analysis failed')
      setAnalysis(row)
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e?.message || String(e))
    }
  }

  const bias = (analysis?.bias || '').toUpperCase()
  const biasClass = BIAS_CLASS[bias] || ''

  return (
    <section className="claude-panel">
      <div className="claude-head">
        <h3>Claude AI · reads TradingView chart</h3>
        <button type="button" className="claude-analyze-btn" disabled={status === 'loading'} onClick={analyze}>
          {status === 'loading' ? 'Reading chart…' : 'Ask Claude'}
        </button>
      </div>
      <p className="meta claude-hint">
        Claude analyzes the same live gold OHLC as this chart (GC=F / PAXG) plus desk session, EMA/RSI,
        and recent signals. Optional: point TradingView alerts to{' '}
        <code>/api/webhooks/tradingview?secret=YOUR_SECRET</code>.
      </p>
      {status === 'off' || status === 'error' ? (
        <p className="meta claude-error">{error || 'Claude unavailable'}</p>
      ) : null}
      {analysis ? (
        <div className={`claude-box action-${bias.toLowerCase()}`}>
          <div className="auto-head">
            <strong>{bias || '—'}</strong>
            <span className={`side ${biasClass}`}>{analysis.model || 'Claude'}</span>
          </div>
          <p className="auto-reason">{analysis.summary}</p>
          {analysis.structure ? (
            <p className="meta">
              <strong>Structure:</strong> {analysis.structure}
            </p>
          ) : null}
          {analysis.levels ? (
            <p className="meta">
              S {analysis.levels.support ?? '—'} · R {analysis.levels.resistance ?? '—'} · inv{' '}
              {analysis.levels.invalidation ?? '—'}
            </p>
          ) : null}
          {(analysis.confluence || []).length ? (
            <ul className="ai-reasons">
              {analysis.confluence.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
          {(analysis.risk_notes || []).length ? (
            <ul className="ai-reasons claude-risks">
              {analysis.risk_notes.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : status === 'idle' ? (
        <p className="meta">Press Ask Claude to read the current {interval === '60' ? '1h' : `${interval}m`} chart.</p>
      ) : null}
    </section>
  )
}
