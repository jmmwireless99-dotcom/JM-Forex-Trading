import { useEffect, useState } from 'react'
import { Link } from '../Nav.jsx'
import { labApi } from '../api.js'

export default function HomePage() {
  const [online, setOnline] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    labApi
      .status()
      .then((s) => {
        if (alive) {
          setOnline(Boolean(s?.running))
          setErr('')
        }
      })
      .catch((e) => {
        if (alive) {
          setOnline(false)
          setErr(e.message || 'Cannot reach JM FX API')
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
          Experimental UI for pair research, bot comparisons, and sandbox ideas.
          The production gold desk at{' '}
          <a href="/fx/" className="lab-link">
            /fx/
          </a>{' '}
          is not changed by anything here.
        </p>
        <div className="lab-pills">
          <span className={`lab-pill ${online === true ? 'ok' : online === false ? 'warn' : ''}`}>
            JM FX API:{' '}
            {online === null ? 'checking…' : online ? 'online (read-only)' : 'offline'}
          </span>
          <span className="lab-pill">Lab v0.1 · demo experiments</span>
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
            {['EURUSD', 'GBPUSD', 'AUDNZD', 'EURCHF'].map((id) => (
              <a key={id} href={`/lab/${id}`} className="lab-btn lab-btn-ghost" target="_blank" rel="noopener noreferrer">
                /lab/{id}
              </a>
            ))}
          </div>
        </article>
        <article className="lab-card">
          <h2>Bot comparison</h2>
          <p>JM FX gold stack vs generic Scalper, Grid, and Trend EAs — side by side.</p>
          <Link to="compare" className="lab-btn">
            Open comparison
          </Link>
        </article>
        <article className="lab-card">
          <h2>JM FX snapshot</h2>
          <p>Live read-only view of session, block reason, and AI stats from the real desk.</p>
          <Link to="snapshot" className="lab-btn">
            View snapshot
          </Link>
        </article>
        <article className="lab-card">
          <h2>Live demo trading</h2>
          <p>
            Paper money with live EUR/USD, GBP/USD, and gold prices — separate lab backend, not JM FX.
          </p>
          <Link to="trade" className="lab-btn">
            Open live demo
          </Link>
        </article>
        <article className="lab-card">
          <h2>Pair sandbox</h2>
          <p>Placeholder for EUR/USD, GBP/USD, and other pair experiments.</p>
          <Link to="pairs" className="lab-btn lab-btn-ghost">
            Pair lab
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
