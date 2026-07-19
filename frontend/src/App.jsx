import { useEffect, useState } from 'react'
import { api, connectFeed } from './api'
import './App.css'

const emptyAccount = {
  balance: 0,
  equity: 0,
  free_margin: 0,
  daily_pnl: 0,
  open_positions: 0,
  currency: 'USD',
}

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function pnlClass(n) {
  if (n > 0) return 'positive'
  if (n < 0) return 'negative'
  return ''
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [account, setAccount] = useState(emptyAccount)
  const [ticks, setTicks] = useState({})
  const [positions, setPositions] = useState([])
  const [signals, setSignals] = useState([])
  const [strategies, setStrategies] = useState([])
  const [strategy, setStrategy] = useState('ema_crossover')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [st, acc, pos, sig, tk, strat] = await Promise.all([
          api.status(),
          api.account(),
          api.positions(),
          api.signals(),
          api.ticks(),
          api.strategies(),
        ])
        if (!alive) return
        setStatus(st)
        setAccount(acc)
        setPositions(pos.open || [])
        setSignals(sig.signals || [])
        setStrategies(strat.strategies || [])
        if (st.active_strategy) setStrategy(st.active_strategy)
        const map = {}
        for (const t of tk.ticks || []) map[t.symbol] = t
        setTicks(map)
      } catch (err) {
        if (alive) setError(err.message || 'Failed to load API')
      }
    })()

    const disconnect = connectFeed((msg) => {
      if (!alive) return
      if (msg.event === 'engine') setStatus(msg.data)
      if (msg.event === 'account') setAccount(msg.data)
      if (msg.event === 'positions') setPositions(msg.data || [])
      if (msg.event === 'tick') {
        setTicks((prev) => ({ ...prev, [msg.data.symbol]: msg.data }))
      }
      if (msg.event === 'signal') {
        setSignals((prev) => [msg.data, ...prev].slice(0, 40))
      }
      if (msg.event === 'position_closed') {
        setPositions((prev) => prev.filter((p) => p.id !== msg.data.id))
      }
    })

    return () => {
      alive = false
      disconnect()
    }
  }, [])

  async function run(action) {
    setBusy(true)
    setError('')
    try {
      const next = await action()
      if (next) setStatus(next)
    } catch (err) {
      setError(err.message || 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function onClose(id) {
    await run(async () => {
      await api.closePosition(id)
      const pos = await api.positions()
      setPositions(pos.open || [])
      setAccount(await api.account())
      return null
    })
  }

  return (
    <div className="app">
      <header className="hero">
        <div className="brand-lockup">
          <h1 className="brand">
            JM <span>Forex</span>
          </h1>
          <div className="mode-chip">
            {status?.running ? 'Automation live' : 'Engine paused'} · paper
          </div>
        </div>
        <p>
          Automated FX execution desk — strategy signals, hard risk gates, and
          paper fills streaming in real time.
        </p>
        <div className="controls">
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            disabled={busy}
          >
            {(strategies.length ? strategies : ['ema_crossover', 'rsi_mean_reversion']).map(
              (name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ),
            )}
          </select>
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api.setStrategy(strategy)
                return api.start(strategy)
              })
            }
          >
            Start engine
          </button>
          <button
            className="btn-danger"
            disabled={busy || !status?.running}
            onClick={() => run(() => api.stop())}
          >
            Stop
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api.setStrategy(strategy)
                return api.status()
              })
            }
          >
            Apply strategy
          </button>
        </div>
        {error ? <div className="error-banner">{error}</div> : null}
        <div className="status-row">
          <span>Strategy: {status?.active_strategy || '—'}</span>
          <span>Ticks: {status?.ticks_processed ?? 0}</span>
          <span>Uptime: {status?.uptime_seconds ?? 0}s</span>
        </div>
      </header>

      <section className="metrics" aria-label="Account metrics">
        <div className="metric">
          <label>Equity</label>
          <strong>${money(account.equity)}</strong>
        </div>
        <div className="metric">
          <label>Balance</label>
          <strong>${money(account.balance)}</strong>
        </div>
        <div className="metric">
          <label>Daily P&amp;L</label>
          <strong className={pnlClass(account.daily_pnl)}>
            ${money(account.daily_pnl)}
          </strong>
        </div>
        <div className="metric">
          <label>Open</label>
          <strong>{account.open_positions}</strong>
        </div>
      </section>

      <div className="layout">
        <section className="panel">
          <h2>Live markets</h2>
          <div className="tick-grid">
            {Object.values(ticks).length === 0 ? (
              <div className="empty">Waiting for market ticks…</div>
            ) : (
              Object.values(ticks).map((t) => (
                <div className="tick" key={t.symbol}>
                  <div className="sym">{t.symbol}</div>
                  <div className="px">{t.mid}</div>
                  <div className="spread">
                    {t.bid} / {t.ask}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <h2>Signals</h2>
          <div className="signal-list">
            {signals.length === 0 ? (
              <div className="empty">No strategy signals yet.</div>
            ) : (
              signals.map((s, i) => (
                <div className="signal" key={`${s.timestamp}-${i}`}>
                  <span className={`side ${s.side.toLowerCase()}`}>{s.side}</span>
                  <div>
                    <div>
                      <strong>{s.symbol}</strong> · {s.strategy}
                    </div>
                    <div className="meta">{s.reason}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel" style={{ gridColumn: '1 / -1' }}>
          <h2>Open positions</h2>
          {positions.length === 0 ? (
            <div className="empty">Flat — no open exposure.</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Lots</th>
                  <th>Entry</th>
                  <th>SL / TP</th>
                  <th>uP&amp;L</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.id}>
                    <td>{p.symbol}</td>
                    <td>
                      <span className={`side ${p.side.toLowerCase()}`}>{p.side}</span>
                    </td>
                    <td>{p.lots}</td>
                    <td>{p.entry_price}</td>
                    <td>
                      {p.stop_loss ?? '—'} / {p.take_profit ?? '—'}
                    </td>
                    <td className={pnlClass(p.unrealized_pnl)}>
                      ${money(p.unrealized_pnl)}
                    </td>
                    <td>
                      <button className="btn-ghost" onClick={() => onClose(p.id)}>
                        Close
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <p className="footer-note">
        Paper mode only. JM Forex automation never places live broker orders from
        this build — connect a real broker adapter when you are ready to go live.
      </p>
    </div>
  )
}