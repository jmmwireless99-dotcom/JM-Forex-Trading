import { PAIR_GUIDE, LAB_TIPS } from '../content/compare.js'

export default function PairLabPage() {
  return (
    <div className="lab-page">
      <header className="lab-page-head">
        <h1>Pair lab — automation guide</h1>
        <p className="lab-muted">
          Which forex pair fits which EA style. Paper trade on{' '}
          <a href="#trade" className="lab-link">
            Live demo
          </a>{' '}
          — separate from JM FX gold.
        </p>
      </header>

      <div className="lab-card-grid">
        {PAIR_GUIDE.map((p) => (
          <article key={p.id} className="lab-card">
            <div className="lab-pair-head">
              <h2>{p.label}</h2>
              <span className={`lab-tag lab-tag-${p.status}`}>{p.status}</span>
            </div>
            <p>
              <strong>Bot style:</strong> {p.botStyle}
            </p>
            <p className="lab-muted">
              Spread: {p.spread} · Session: {p.session}
            </p>
            <p className="lab-muted">Lab auto: {p.labAuto} · Risk: {p.risk}</p>
            <p>{p.note}</p>
            {p.id !== 'XAUUSD' ? (
              <a
                href="#trade"
                className="lab-btn"
                onClick={(e) => {
                  e.preventDefault()
                  try {
                    sessionStorage.setItem('jm_lab_trade_symbol', p.id)
                  } catch {
                    /* ignore */
                  }
                  window.location.hash = 'trade'
                }}
              >
                Demo trade {p.label}
              </a>
            ) : (
              <a href="/fx/" className="lab-btn lab-btn-ghost">
                JM FX gold desk ↗
              </a>
            )}
          </article>
        ))}
      </div>

      <section className="lab-callout">
        <h2>Before you run any EA bot (live)</h2>
        <ul>
          {LAB_TIPS.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </section>

      <section className="lab-disclaimer">
        <strong>Disclaimer:</strong> Grid/martingale can wipe accounts. Lab is educational paper money only.
      </section>
    </div>
  )
}
