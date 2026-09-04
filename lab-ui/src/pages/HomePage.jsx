import { useEffect, useState } from 'react'
import { Link } from '../Nav.jsx'
import { labTradeApi } from '../api.js'
import { PAIR_URL_SYMBOLS, pairTradePath } from '../routing.js'

export default function HomePage() {
  const [online, setOnline] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    labTradeApi
      .health()
      .then(() => {
        if (alive) {
          setOnline(true)
          setErr('')
        }
      })
      .catch((e) => {
        if (alive) {
          setOnline(false)
          setErr(e.message || 'Cannot reach Lab API')
        }
      })
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="lab-page">
      <section className="lab-hero">
        <p className="lab-kicker">4-pair paper lab</p>
        <h1>JM Lab</h1>
        <p className="lab-lead">
          Separate demo backend for EUR/USD, AUD/NZD, EUR/CHF, and XAUUSD scalping experiments.
          Each pair has its own strategy, account, and auto-trader — not connected to any live desk.
        </p>
        <div className="lab-pills">
          <span className={`lab-pill ${online === true ? 'ok' : online === false ? 'warn' : ''}`}>
            Lab API: {online === null ? 'checking…' : online ? 'online' : 'offline'}
          </span>
          <span className="lab-pill">Paper only · 0.03 lot presets</span>
        </div>
        {err ? <p className="lab-error-inline">{err}</p> : null}
      </section>

      <section className="lab-card-grid">
        <article className="lab-card lab-card-wide">
          <h2>Per-pair demo URLs</h2>
          <p>
            Buksan bawat pair sa hiwalay na tab — may sariling account at auto-trader bawat isa.
          </p>
          <div className="lab-pair-url-grid">
            {PAIR_URL_SYMBOLS.map((id) => (
              <a
                key={id}
                href={pairTradePath(id)}
                className="lab-btn lab-btn-ghost"
                target="_blank"
                rel="noopener noreferrer"
              >
                /lab/{id}
              </a>
            ))}
          </div>
        </article>
        <article className="lab-card">
          <h2>4-pair dashboard</h2>
          <p>Live status for all lab pairs — auto, block reason, open positions, and P&amp;L.</p>
          <Link to="suite" className="lab-btn">
            Open dashboard
          </Link>
        </article>
        <article className="lab-card">
          <h2>Live demo trading</h2>
          <p>Paper money with live market prices on the lab backend — pick a pair and start auto.</p>
          <Link to="trade" className="lab-btn">
            Open live demo
          </Link>
        </article>
        <article className="lab-card">
          <h2>Pair strategies</h2>
          <p>Which bot style fits each pair — EMA+RSI scalper, mean revert, gold trend.</p>
          <Link to="pairs" className="lab-btn lab-btn-ghost">
            Pair lab guide
          </Link>
        </article>
      </section>

      <section className="lab-disclaimer">
        <strong>Disclaimer:</strong> Educational and experimental only. Not financial advice.
        Do not run grid/martingale on live accounts without extensive demo testing.
      </section>
    </div>
  )
}
