import { useEffect, useState } from 'react'
import { Link } from '../Nav.jsx'
import { labTradeApi } from '../api.js'

export default function HomePage() {
  const [online, setOnline] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    labTradeApi
      .health()
      .then((s) => {
        if (alive) {
          setOnline(s?.status === 'ok')
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
        <p className="lab-kicker">Separate from JM FX desk</p>
        <h1>JM Lab</h1>
        <p className="lab-lead">
          4-pair paper trading sandbox — EUR/USD, AUD/NZD, EUR/CHF, and XAUUSD each run their
          own scalping strategy on the lab backend. The production gold desk at{' '}
          <a href="/fx/" className="lab-link">
            /fx/
          </a>{' '}
          is not controlled from here.
        </p>
        <div className="lab-pills">
          <span className={`lab-pill ${online === true ? 'ok' : online === false ? 'warn' : ''}`}>
            Lab API: {online === null ? 'checking…' : online ? 'online' : 'offline'}
          </span>
          <span className="lab-pill">4 pairs · demo · isolated backend</span>
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
            {['EURUSD', 'AUDNZD', 'EURCHF', 'XAUUSD'].map((id) => (
              <a key={id} href={`/lab/${id}`} className="lab-btn lab-btn-ghost" target="_blank" rel="noopener noreferrer">
                /lab/{id}
              </a>
            ))}
          </div>
        </article>
        <article className="lab-card">
          <h2>4-pair test</h2>
          <p>Run all four pairs in parallel — one demo account per symbol.</p>
          <Link to="suite" className="lab-btn">
            Open 4-pair suite
          </Link>
        </article>
        <article className="lab-card">
          <h2>Lab status</h2>
          <p>Auto-trader block reasons, equity, and last signals for each pair.</p>
          <Link to="snapshot" className="lab-btn">
            View status
          </Link>
        </article>
        <article className="lab-card">
          <h2>Live demo trading</h2>
          <p>
            Paper money with live EUR/USD, AUD/NZD, EUR/CHF, and gold prices — lab backend only.
          </p>
          <Link to="trade" className="lab-btn">
            Open live demo
          </Link>
        </article>
        <article className="lab-card">
          <h2>Bot comparison</h2>
          <p>Scalper vs mean-revert vs gold trend presets — side by side.</p>
          <Link to="compare" className="lab-btn lab-btn-ghost">
            Open comparison
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
