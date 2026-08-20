import { useCallback, useEffect, useState } from 'react'
import LabCandleChart from '../LabCandleChart.jsx'
import { labTradeApi, loadLabSession, saveLabSession } from '../api.js'

const PAIRS = ['EURUSD', 'GBPUSD', 'XAUUSD']

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function fmtPrice(symbol, n) {
  const d = symbol === 'XAUUSD' ? 2 : 5
  return Number(n || 0).toFixed(d)
}

export default function TradePage() {
  const [session, setSession] = useState(() => loadLabSession())
  const [symbol, setSymbol] = useState('EURUSD')
  const [account, setAccount] = useState(null)
  const [auto, setAuto] = useState(null)
  const [ticks, setTicks] = useState({})
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [lots, setLots] = useState('0.01')
  const [slPips, setSlPips] = useState('15')
  const [tpPips, setTpPips] = useState('30')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const refresh = useCallback(async () => {
    if (!session) return
    const [acc, pos, tr, tk, au] = await Promise.all([
      labTradeApi.account(),
      labTradeApi.positions(),
      labTradeApi.trades(),
      labTradeApi.ticks(),
      labTradeApi.auto(),
    ])
    setAccount(acc)
    setAuto(au)
    setPositions(pos.positions || [])
    setTrades(tr.trades || [])
    setTicks(tk.ticks || {})
  }, [session])

  useEffect(() => {
    if (!session) return undefined
    let alive = true
    ;(async () => {
      try {
        await refresh()
        if (alive) setError('')
      } catch (e) {
        if (alive) setError(e.message || String(e))
      }
    })()
    const id = setInterval(() => {
      refresh().catch(() => {})
    }, 4000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [session, refresh])

  async function createDemo() {
    setBusy(true)
    setError('')
    try {
      const res = await labTradeApi.createAccount(10000, 'Lab live demo')
      const s = {
        account_id: res.account.account_id,
        token: res.token,
        code: res.account.code,
      }
      saveLabSession(s)
      setSession(s)
      setAccount(res.account)
      setNote(res.message || 'Demo account ready')
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    saveLabSession(null)
    setSession(null)
    setAccount(null)
    setAuto(null)
    setPositions([])
    setTrades([])
  }

  function pipSize(sym) {
    return sym === 'XAUUSD' ? 0.01 : 0.0001
  }

  function levels(side, mid) {
    const pip = pipSize(symbol)
    const sl = Number(slPips) * pip
    const tp = Number(tpPips) * pip
    if (!Number.isFinite(sl) || !Number.isFinite(tp)) return { stop_loss: null, take_profit: null }
    if (side === 'BUY') {
      return { stop_loss: mid - sl, take_profit: mid + tp }
    }
    return { stop_loss: mid + sl, take_profit: mid - tp }
  }

  async function order(side) {
    setBusy(true)
    setError('')
    try {
      const mid = ticks[symbol]?.mid
      if (mid == null) throw new Error('Waiting for live price…')
      const lv = levels(side, mid)
      await labTradeApi.marketOrder({
        symbol,
        side,
        lots: Number(lots),
        stop_loss: lv.stop_loss,
        take_profit: lv.take_profit,
      })
      setNote(`${side} ${symbol} · ${lots} lot(s)`)
      await refresh()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  async function closeOpen(id) {
    setBusy(true)
    setError('')
    try {
      await labTradeApi.closePosition(id)
      setNote('Position closed')
      await refresh()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  async function toggleAuto(on) {
    setBusy(true)
    setError('')
    try {
      const res = await labTradeApi.setAuto({
        enabled: on,
        symbol,
        lots: Number(lots),
        sl_pips: Number(slPips),
        tp_pips: Number(tpPips),
      })
      setAuto(res.auto)
      setNote(on ? `Auto EMA+RSI ON · ${symbol}` : 'Auto trading OFF')
      await refresh()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  const tick = ticks[symbol]
  const open = positions.filter((p) => p.status === 'OPEN')

  if (!session) {
    return (
      <div className="lab-page">
        <header className="lab-page-head">
          <h1>Live demo trading</h1>
          <p className="lab-muted">
            Paper money · live market prices · separate from JM FX gold desk.
          </p>
        </header>
        <section className="lab-panel lab-trade-start">
          <h2>Start lab demo account</h2>
          <p>$10,000 virtual balance · EUR/USD · GBP/USD · XAUUSD · chart + auto EMA+RSI</p>
          <button type="button" className="lab-btn" disabled={busy} onClick={createDemo}>
            Create demo account
          </button>
          {error ? <p className="lab-error-inline">{error}</p> : null}
        </section>
      </div>
    )
  }

  return (
    <div className="lab-page">
      <header className="lab-page-head lab-trade-head">
        <div>
          <h1>Live demo trading</h1>
          <p className="lab-muted">
            Account <strong>{session.code}</strong> · paper only · max 1 open position
          </p>
        </div>
        <button type="button" className="lab-btn lab-btn-ghost" onClick={logout}>
          New account
        </button>
      </header>

      {error ? <div className="lab-error-box">{error}</div> : null}
      {note ? <p className="lab-note">{note}</p> : null}

      <div className="lab-stat-grid">
        <article className="lab-stat">
          <span className="lab-stat-label">Balance</span>
          <strong>${money(account?.balance)}</strong>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Equity</span>
          <strong>${money(account?.equity)}</strong>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">Daily P&amp;L</span>
          <strong className={account?.daily_pnl >= 0 ? 'lab-pos' : 'lab-neg'}>
            ${money(account?.daily_pnl)}
          </strong>
        </article>
        <article className="lab-stat">
          <span className="lab-stat-label">{symbol} live</span>
          <strong>{tick ? fmtPrice(symbol, tick.mid) : '—'}</strong>
        </article>
      </div>

      <section className="lab-panel lab-chart-panel">
        <div className="lab-pair-bar">
          {PAIRS.map((p) => (
            <button
              key={p}
              type="button"
              className={symbol === p ? 'on' : ''}
              onClick={() => setSymbol(p)}
            >
              {p}
            </button>
          ))}
        </div>
        <LabCandleChart symbol={symbol} livePrice={tick?.mid} positions={open} />
      </section>

      <section className="lab-panel">
        <div className="lab-auto-head">
          <h2>Auto EMA+RSI</h2>
          <span className={`lab-auto-pill ${auto?.enabled ? 'on' : ''}`}>
            {auto?.enabled ? 'Running' : 'Off'}
          </span>
        </div>
        <p className="lab-muted lab-auto-desc">
          M5 EMA 20/50 + RSI 14 (JM FX style). Auto-fills on new bar when flat.
        </p>
        {auto?.last_block_reason ? (
          <p className="lab-block-reason">{auto.last_block_reason}</p>
        ) : null}
        <div className="lab-trade-controls">
          <label>
            Lots
            <input type="number" step="0.01" min="0.01" value={lots} onChange={(e) => setLots(e.target.value)} />
          </label>
          <label>
            SL (pips)
            <input type="number" step="1" min="0" value={slPips} onChange={(e) => setSlPips(e.target.value)} />
          </label>
          <label>
            TP (pips)
            <input type="number" step="1" min="0" value={tpPips} onChange={(e) => setTpPips(e.target.value)} />
          </label>
          {!auto?.enabled ? (
            <button type="button" className="lab-btn" disabled={busy} onClick={() => toggleAuto(true)}>
              Start auto
            </button>
          ) : (
            <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => toggleAuto(false)}>
              Stop auto
            </button>
          )}
        </div>
        {(auto?.recent_signals || []).length > 0 ? (
          <div className="lab-auto-signals">
            <h3>Auto signals</h3>
            {auto.recent_signals.slice(0, 5).map((s) => (
              <div key={`${s.at}-${s.side}`} className="lab-trade-row">
                <span>
                  {s.side} {s.symbol} · {s.reason}
                </span>
                <span className="lab-muted">{s.at ? new Date(s.at).toLocaleString() : ''}</span>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="lab-panel">
        <h2>Manual trade</h2>
        <div className="lab-trade-controls">
          <button type="button" className="lab-btn lab-buy" disabled={busy || open.length > 0} onClick={() => order('BUY')}>
            Buy
          </button>
          <button type="button" className="lab-btn lab-sell" disabled={busy || open.length > 0} onClick={() => order('SELL')}>
            Sell
          </button>
        </div>
      </section>

      <section className="lab-panel">
        <h2>Open positions</h2>
        {open.length === 0 ? (
          <p className="lab-muted">Flat — no open exposure.</p>
        ) : (
          open.map((p) => (
            <div key={p.id} className="lab-trade-row">
              <span>
                {p.side} {p.symbol} · {p.lots} @ {fmtPrice(p.symbol, p.entry_price)}
              </span>
              <span className={p.unrealized_pnl >= 0 ? 'lab-pos' : 'lab-neg'}>
                uP&amp;L ${money(p.unrealized_pnl)}
              </span>
              <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => closeOpen(p.id)}>
                Close
              </button>
            </div>
          ))
        )}
      </section>

      <section className="lab-panel">
        <h2>Trade log</h2>
        {trades.length === 0 ? (
          <p className="lab-muted">No closed trades yet.</p>
        ) : (
          <div className="lab-table-wrap">
            <table className="lab-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Pair</th>
                  <th>Side</th>
                  <th>Lots</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((t) => (
                  <tr key={`${t.id}-${t.closed_at}`}>
                    <td>{t.closed_at ? new Date(t.closed_at).toLocaleString() : '—'}</td>
                    <td>{t.symbol}</td>
                    <td>{t.side}</td>
                    <td>{t.lots}</td>
                    <td className={t.pnl >= 0 ? 'lab-pos' : 'lab-neg'}>${money(t.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
