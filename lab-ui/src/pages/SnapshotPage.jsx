import { useEffect, useState } from 'react'
import { labApi } from '../api.js'

function sessionLabel(label) {
  const map = {
    asia: 'Asia · EMA_RSI',
    london_ny_overlap: 'Overlap · SMC',
    new_york: 'NY · VWAP',
    off_hours: 'Off-hours',
    weekend: 'Weekend',
  }
  return map[label] || label || '—'
}

export default function SnapshotPage() {
  const [desk, setDesk] = useState(null)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [d, s] = await Promise.all([labApi.desk(), labApi.status()])
        if (!alive) return
        setDesk(d)
        setStatus(s)
        setError('')
      } catch (e) {
        if (!alive) return
        setError(e.message || String(e))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    const id = setInterval(async () => {
      try {
        const d = await labApi.desk()
        if (alive) setDesk(d)
      } catch {
        /* ignore refresh errors */
      }
    }, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  if (loading) return <p className="lab-loading">Loading JM FX snapshot…</p>
  if (error) {
    return (
      <div className="lab-page">
        <div className="lab-error-box">
          <p>Could not load JM FX API (read-only).</p>
          <p className="lab-muted">{error}</p>
          <p className="lab-muted">
            Local dev: start the JM FX backend on port 8000, or set VITE_JM_API to your desk URL.
          </p>
        </div>
      </div>
    )
  }

  const rec = desk?.recommended_now || {}
  const ai = desk?.ai || {}
  const hist = ai.history || {}

  return (
    <div className="lab-page">
      <header className="lab-page-head">
        <h1>JM FX live snapshot</h1>
        <p className="lab-muted">Read-only mirror — production desk is not controlled from Lab.</p>
      </header>

      <div className="lab-stat-grid">
        <article className="lab-stat">
          <span className="lab-stat-label">Engine</span>
          <strong>{status?.running ? 'Running' : 'Stopped'}</strong>
          <span className="lab-muted">{status?.mode || '—'} · {status?.active_strategy}</span>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Session</span>
          <strong>{sessionLabel(rec.session || desk?.session?.label)}</strong>
          <span className="lab-muted">{desk?.session?.reason}</span>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Active stack</span>
          <strong>{rec.display || rec.child_strategy || '—'}</strong>
          <span className="lab-muted">Auto: {desk?.auto?.enabled ? 'ON' : 'OFF'}</span>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Gold mid (paper)</span>
          <strong>
            {status?.connection?.paper_mid != null
              ? Number(status.connection.paper_mid).toFixed(2)
              : '—'}
          </strong>
          <span className="lab-muted">Signal TF: {desk?.signal_timeframe || 'M5'}</span>
        </article>
      </div>

      <section className="lab-panel">
        <h2>Last block / checklist</h2>
        <p className="lab-block-reason">{desk?.last_block_reason || 'No block reason recorded'}</p>
        {desk?.entry_checklist?.length ? (
          <ul className="lab-checklist">
            {desk.entry_checklist.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="lab-panel">
        <h2>AI &amp; ML history (from production desk)</h2>
        <div className="lab-stat-grid lab-stat-grid-3">
          <article className="lab-stat">
            <span className="lab-stat-label">Labeled trades</span>
            <strong>{hist.labeled ?? '—'}</strong>
          </article>
          <article className="lab-stat">
            <span className="lab-stat-label">Win rate</span>
            <strong>{hist.win_rate_pct != null ? `${hist.win_rate_pct}%` : '—'}</strong>
          </article>
          <article className="lab-stat">
            <span className="lab-stat-label">Asia WR</span>
            <strong>
              {hist.by_session?.asia?.win_rate_pct != null
                ? `${hist.by_session.asia.win_rate_pct}%`
                : '—'}
            </strong>
          </article>
        </div>
      </section>

      <p className="lab-muted lab-foot">
        Open full desk:{' '}
        <a href="/fx/" className="lab-link">
          jmtechsolution.cloud/fx/
        </a>
      </p>
    </div>
  )
}
