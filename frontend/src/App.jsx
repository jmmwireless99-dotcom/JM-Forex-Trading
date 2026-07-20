import { useEffect, useState } from 'react'
import { api, connectFeed } from './api'
import CandleChart from './CandleChart'
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
  const [desk, setDesk] = useState(null)
  const [mt, setMt] = useState(null)
  const [account, setAccount] = useState(emptyAccount)
  const [ticks, setTicks] = useState({})
  const [positions, setPositions] = useState([])
  const [signals, setSignals] = useState([])
  const [strategies, setStrategies] = useState([])
  const [strategy, setStrategy] = useState('gold_confluence')
  const [mode, setMode] = useState('paper')
  const [candles, setCandles] = useState([])
  const [liveCandle, setLiveCandle] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [st, acc, pos, sig, tk, strat, deskInfo, mtInfo, candleInfo] =
          await Promise.all([
            api.status(),
            api.account(),
            api.positions(),
            api.signals(),
            api.ticks(),
            api.strategies(),
            api.desk(),
            api.mtStatus(),
            api.candles('XAUUSD', 200),
          ])
        if (!alive) return
        setStatus(st)
        setAccount(acc)
        setPositions(pos.open || [])
        setSignals(sig.signals || [])
        setStrategies(strat.strategies || [])
        setDesk(deskInfo)
        setMt(mtInfo)
        setMode(st.mode || st.connection?.mode || 'paper')
        setCandles(candleInfo.candles || [])
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
      if (msg.event === 'engine') {
        setStatus(msg.data)
        if (msg.data?.mode) setMode(msg.data.mode)
      }
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
      if (msg.event === 'connection') {
        setMt((prev) => ({ ...(prev || {}), ...msg.data }))
        if (msg.data?.mode) setMode(msg.data.mode)
      }
      if (msg.event === 'candles') {
        setCandles(msg.data.candles || [])
      }
      if (msg.event === 'candle') {
        setLiveCandle(msg.data)
        setCandles((prev) => {
          const next = [...prev]
          const idx = next.findIndex(
            (c) => (c.open_time || c.timestamp) === (msg.data.open_time || msg.data.timestamp),
          )
          if (idx >= 0) next[idx] = msg.data
          else next.push(msg.data)
          return next.slice(-240)
        })
      }
      if (msg.event === 'candle_closed') {
        setCandles((prev) => {
          const next = prev.filter(
            (c) => (c.open_time || c.timestamp) !== (msg.data.open_time || msg.data.timestamp),
          )
          next.push(msg.data)
          return next.slice(-240)
        })
      }
    })

    const deskTimer = setInterval(() => {
      api.desk().then((d) => alive && setDesk(d)).catch(() => {})
      api.mtStatus().then((m) => alive && setMt(m)).catch(() => {})
    }, 10000)

    return () => {
      alive = false
      disconnect()
      clearInterval(deskTimer)
    }
  }, [])

  async function run(action) {
    setBusy(true)
    setError('')
    try {
      const next = await action()
      if (next?.running !== undefined || next?.mode) setStatus(next)
      if (next?.status) setStatus(next.status)
      setDesk(await api.desk())
      setMt(await api.mtStatus())
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

  const sessionTier = desk?.session?.tier || '—'
  const newsBlocked = Boolean(desk?.news?.blocked)
  const mtOnline = Boolean(mt?.online || mt?.mt_online)
  const gold = ticks.XAUUSD

  return (
    <div className="app">
      <header className="hero">
        <div className="brand-lockup">
          <h1 className="brand">
            JM <span>Forex</span>
          </h1>
          <div className="mode-chip">
            {status?.running ? 'Desk live' : 'Paused'} · {mode.toUpperCase()}
            {mode !== 'paper' ? (mtOnline ? ' · MT online' : ' · MT offline') : ''}
          </div>
        </div>
        <p>
          XAUUSD automation with MT4/MT5 bridge, confluence strategy, and live
          candle view.
        </p>
        <div className="controls">
          <select value={mode} disabled={busy} onChange={(e) => setMode(e.target.value)}>
            <option value="paper">paper</option>
            <option value="mt4">mt4</option>
            <option value="mt5">mt5</option>
          </select>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() => run(() => api.setExecutionMode(mode))}
          >
            Apply mode
          </button>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            disabled={busy}
          >
            {(strategies.length
              ? strategies
              : ['gold_confluence', 'gold_atr_trend', 'ema_crossover', 'rsi_mean_reversion']
            ).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
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
        </div>
        {error ? <div className="error-banner">{error}</div> : null}
        <div className="status-row">
          <span>Strategy: {status?.active_strategy || '—'}</span>
          <span>Session: {sessionTier}</span>
          <span>News: {newsBlocked ? 'BLACKOUT' : 'clear'}</span>
          <span>
            MT: {mtOnline ? 'online' : mt?.configured || mt?.mt_configured ? 'offline' : 'not configured'}
          </span>
          {gold ? <span>XAUUSD {gold.mid}</span> : null}
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

      <section className="chart-panel">
        <CandleChart candles={candles} liveCandle={liveCandle} symbol="XAUUSD" />
      </section>

      <div className="layout">
        <section className="panel">
          <h2>MT4 / MT5</h2>
          <div className="signal-list">
            <div className="signal">
              <span className={`side ${mtOnline ? 'buy' : 'sell'}`}>
                {mtOnline ? 'ON' : 'OFF'}
              </span>
              <div>
                <div>
                  <strong>{(mt?.platform || mode || 'paper').toUpperCase()}</strong>
                </div>
                <div className="meta">
                  {mt?.bridge_dir || 'Set JM_MT4_BRIDGE_DIR / JM_MT5_BRIDGE_DIR on server'}
                </div>
                <div className="meta">
                  Install EA: mt4/Experts/JM_Forex_Bridge.mq4 or mt5/Experts/JM_Forex_Bridge.mq5
                </div>
              </div>
            </div>
            {desk?.last_block_reason ? (
              <div className="meta" style={{ color: '#ffb4b4' }}>
                Last block: {desk.last_block_reason}
              </div>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <h2>Signals</h2>
          <div className="signal-list">
            {signals.length === 0 ? (
              <div className="empty">Waiting for confluence signals…</div>
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
        Part of{' '}
        <a href="https://jmtechsolution.cloud" style={{ color: '#7dffb3' }}>
          JM TECH SOLUTION
        </a>
        {' '}
        · paper / MT4 / MT5 · live candles · gold_confluence
      </p>
    </div>
  )
}
