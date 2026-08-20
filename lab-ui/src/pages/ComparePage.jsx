import { BOT_ROWS } from '../content/compare.js'

export default function ComparePage() {
  return (
    <div className="lab-page">
      <header className="lab-page-head">
        <h1>Bot comparison</h1>
        <p className="lab-muted">
          How JM FX (gold) differs from typical MetaTrader EAs. Static reference — not live trading.
        </p>
      </header>

      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Bot type</th>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Spread</th>
              <th>Session</th>
              <th>Blow-up risk</th>
              <th>Martingale</th>
              <th>Lab note</th>
            </tr>
          </thead>
          <tbody>
            {BOT_ROWS.map((row) => (
              <tr key={row.id} className={row.highlight ? 'lab-row-highlight' : ''}>
                <td>
                  <strong>{row.name}</strong>
                </td>
                <td>{row.symbol}</td>
                <td>{row.type}</td>
                <td>{row.spread}</td>
                <td>{row.session}</td>
                <td>{row.blowUp}</td>
                <td>{row.martingale}</td>
                <td className="lab-muted">{row.verdict}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="lab-callout">
        <h2>Why JM FX stays on gold</h2>
        <ul>
          <li>Session map tuned for Manila hours (EMA_RSI → SMC → VWAP).</li>
          <li>AI_ML filter learns from your closed SL/TP history.</li>
          <li>No grid/martingale — max 1 open position by default.</li>
          <li>Other pairs belong in this Lab until a separate backend is built.</li>
        </ul>
      </section>
    </div>
  )
}
