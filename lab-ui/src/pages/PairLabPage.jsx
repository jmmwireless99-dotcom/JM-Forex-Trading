import { PAIR_GUIDE, LAB_TIPS } from '../content/compare.js'
import { pairTradePath } from '../routing.js'

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
          or open a dedicated pair URL below.
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
            <a href={pairTradePath(p.id)} className="lab-btn">
              Demo trade {p.label}
            </a>
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
