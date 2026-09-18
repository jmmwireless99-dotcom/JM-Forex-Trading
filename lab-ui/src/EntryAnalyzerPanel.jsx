function verdictClass(v) {
  if (v === 'OK') return 'ok'
  if (v === 'WEAK') return 'weak'
  if (v === 'MALI') return 'mali'
  return 'wait'
}

function SideRow({ row }) {
  if (!row) return null
  return (
    <div className={`lab-az-side lab-az-${verdictClass(row.verdict)}`}>
      <div className="lab-az-side-top">
        <strong>{row.side}</strong>
        <span className="lab-az-pill">{row.verdict}</span>
        <span className="lab-muted">
          score {row.score}/{row.required}
        </span>
      </div>
      {row.verdict === 'MALI' && (row.reasons || []).length > 0 ? (
        <p className="lab-az-why">Mali dahil: {row.reasons.join(' · ')}</p>
      ) : null}
      {row.verdict === 'WEAK' ? <p className="lab-az-why">Caution — barely passed.</p> : null}
    </div>
  )
}

export default function EntryAnalyzerPanel({ analyzer, error }) {
  if (error) {
    return (
      <section className="lab-panel lab-az">
        <h2>Entry analyzer</h2>
        <p className="lab-error-inline">{error}</p>
      </section>
    )
  }
  if (!analyzer) {
    return (
      <section className="lab-panel lab-az">
        <h2>Entry analyzer</h2>
        <p className="lab-muted">Reading M5 candles…</p>
      </section>
    )
  }

  const v = verdictClass(analyzer.verdict)
  return (
    <section className={`lab-panel lab-az lab-az-panel-${v}`}>
      <div className="lab-az-head">
        <h2>Entry analyzer</h2>
        <span className={`lab-az-pill lab-az-pill-lg lab-az-${v}`}>{analyzer.verdict}</span>
      </div>
      <p className="lab-az-summary">{analyzer.summary}</p>
      <p className="lab-muted lab-az-meta">
        Hour {String(analyzer.hour).padStart(2, '0')}:00 UTC · bias {analyzer.hour_bias}
        {analyzer.adx != null ? ` · ADX ${analyzer.adx}` : ''}
        {analyzer.rsi != null ? ` · RSI ${analyzer.rsi}` : ''}
        {analyzer.ema_fast != null ? ` · EMA ${analyzer.ema_fast}/${analyzer.ema_slow}` : ''}
        {' · '}
        {analyzer.flow_proxy === 'm1' ? 'M1 flow' : 'M5 flow proxy'}
      </p>
      <div className="lab-az-sides">
        <SideRow row={analyzer.buy} />
        <SideRow row={analyzer.sell} />
      </div>
      {(analyzer.checks || []).length > 0 ? (
        <ul className="lab-az-checks">
          {analyzer.checks.map((c) => (
            <li key={c.name} className={`lab-az-${verdictClass(c.verdict)}`}>
              <span>{c.name}</span> {c.detail}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
