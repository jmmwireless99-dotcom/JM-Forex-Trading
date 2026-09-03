import { useEffect, useState } from 'react'
import { labTradeApi } from '../api.js'
import { PAIR_PRESETS } from '../content/compare.js'

function fmtPrice(symbol, n) {
  const d = symbol === 'XAUUSD' ? 2 : 5
  return Number(n || 0).toFixed(d)
}

function fmtMoney(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export default function SnapshotPage() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const s = await labTradeApi.suiteStatus()
        if (!alive) return
        setStatus(s)
        setError('')
      } catch (e) {
        if (!alive) return
        setError(e.message || String(e))
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  if (loading) return <p className="lab-loading">Loading lab suite status…</p>
  if (error) {
    return (
      <div className="lab-page">
        <div className="lab-error-box">
          <p>Could not load Lab API.</p>
          <p className="lab-muted">{error}</p>
          <p className="lab-muted">
            Local dev: start the lab backend on port 8001, or set VITE_LAB_API to your lab URL.
          </p>
        </div>
      </div>
    )
  }

  const pairs = status?.pairs || []

  return (
    <div className="lab-page">
      <header className="lab-page-head">
        <h1>4-pair lab status</h1>
        <p className="lab-muted">
          Live paper suite — EUR/USD, AUD/NZD, EUR/CHF, XAUUSD. Fully separate from JM FX desk.
        </p>
      </header>

      <div className="lab-stat-grid">
        <article className="lab-stat">
          <span className="lab-stat-label">Engine</span>
          <strong>{status?.engine_running ? 'Running' : 'Stopped'}</strong>
          <span className="lab-muted">Lab backend · port 8001</span>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Suite</span>
          <strong>{status?.suite_size ?? 4} pairs</strong>
          <span className="lab-muted">{status?.auto_enabled_count ?? 0} auto ON</span>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Service</span>
          <strong>{status?.service || 'JM Lab Trading'}</strong>
          <span className="lab-muted">Paper money only</span>
        </article>
      </div>

      <div className="lab-card-grid">
        {pairs.map((row) => {
          const sym = row.symbol
          const preset = row.pair_preset || PAIR_PRESETS[sym] || {}
          const acc = row.account
          const auto = row.auto
          const tick = row.tick
          return (
            <article key={sym} className="lab-card">
              <div className="lab-pair-head">
                <h2>{sym}</h2>
                <span className={`lab-tag lab-tag-${auto?.enabled ? 'live' : 'warn'}`}>
                  {auto?.enabled ? 'auto ON' : 'auto OFF'}
                </span>
              </div>
              <p className="lab-muted">
                {preset.label || row.strategy_info?.name} · SL {preset.sl_pips}p / TP{' '}
                {preset.tp_pips}p
              </p>
              <p>
                <strong>Mid:</strong>{' '}
                {tick?.mid != null ? fmtPrice(sym, tick.mid) : '—'}
                {tick?.stale ? ' (stale)' : ''}
              </p>
              {acc ? (
                <>
                  <p>
                    <strong>Account {acc.code}:</strong> ${fmtMoney(acc.equity)} equity ·{' '}
                    {acc.open_positions} open
                  </p>
                  <p className="lab-muted">Daily P&amp;L: ${fmtMoney(acc.daily_pnl)}</p>
                </>
              ) : (
                <p className="lab-muted">No suite account — open 4-pair test to bootstrap.</p>
              )}
              <p className="lab-block-reason">
                {auto?.last_block_reason || 'No block reason — waiting for signal'}
              </p>
              {auto?.recent_signals?.length ? (
                <ul className="lab-checklist">
                  {auto.recent_signals.slice(0, 3).map((sig, i) => (
                    <li key={`${sig.at}-${i}`}>
                      {sig.side} {sig.symbol} · {sig.reason || sig.at}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          )
        })}
      </div>

      <p className="lab-muted lab-foot">
        JM FX production desk (separate):{' '}
        <a href="/fx/" className="lab-link">
          /fx/
        </a>
      </p>
    </div>
  )
}
