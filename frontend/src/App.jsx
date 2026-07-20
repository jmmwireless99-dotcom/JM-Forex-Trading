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
  const [strategy, setStrategy] = useState('auto_gold')
  const [mode, setMode] = useState('paper')
  const [autoInfo, setAutoInfo] = useState(null)
  const [candles, setCandles] = useState([])
  const [liveCandle, setLiveCandle] = useState(null)
  const [trades, setTrades] = useState([])
  const [tradeSummary, setTradeSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [st, acc, pos, sig, tk, strat, deskInfo, mtInfo, candleInfo, tradeInfo, auto] =
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
            api.trades(100),
            api.auto(),
          ])
        if (!alive) return
        setStatus(st)
        setAccount(acc)
        setPositions(pos.open || [])
        setSignals(sig.signals || [])
        setStrategies(strat.strategies || [])
        setDesk(deskInfo)
        setMt(mtInfo)
        setAutoInfo(auto)
        setMode(st.mode || st.connection?.mode || 'paper')
        setCandles(candleInfo.candles || [])
        setTrades(tradeInfo.trades || [])
        setTradeSummary(tradeInfo.summary || null)
        if (st.active_strategy?.startsWith('auto_gold')) setStrategy('auto_gold')
        else if (st.active_strategy) setStrategy(st.active_strategy)
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
      if (msg.event === 'trades') {
        setTrades(msg.data.trades || [])
        setTradeSummary(msg.data.summary || null)
      }
      if (msg.event === 'trade') {
        setTrades((prev) => {
          const rest = prev.filter((t) => t.id !== msg.data.id && t.ticket !== msg.data.ticket)
          return [msg.data, ...rest].slice(0, 100)
        })
      }
      if (msg.event === 'auto') {
        setAutoInfo(msg.data)
        if (msg.data?.enabled) setStrategy('auto_gold')
        else if (msg.data?.active_strategy) setStrategy(msg.data.active_strategy)
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
          XAUUSD auto desk — M5 candle entries only after full checklist
          (trend, pullback, confirm) with structure SL and R-multiple TP.
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
              : ['auto_gold', 'gold_confluence', 'gold_atr_trend', 'ema_crossover', 'rsi_mean_reversion']
            ).map((name) => (
              <option key={name} value={name}>
                {name === 'auto_gold' ? 'auto_gold (recommended)' : name}
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
          <span>Strategy: {status?.active_strategy || autoInfo?.display || '—'}</span>
          <span>
            Slot: {autoInfo?.decision?.slot || desk?.session?.label || '—'} ·{' '}
            {autoInfo?.decision?.regime || sessionTier}
          </span>
          <span>News: {newsBlocked ? 'BLACKOUT' : 'clear'}</span>
          <span>
            MT: {mtOnline ? 'online' : mt?.configured || mt?.mt_configured ? 'offline' : 'not configured'}
          </span>
          {gold ? <span>XAUUSD {gold.mid}</span> : null}
        </div>
        {autoInfo?.decision ? (
          <div className="meta" style={{ marginTop: '0.55rem' }}>
            Auto: {autoInfo.decision.allow_trading ? 'TRADING' : 'STAND ASIDE'} —{' '}
            {autoInfo.decision.reason}
          </div>
        ) : null}
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
          <h2>Auto schedule · {desk?.signal_timeframe || 'M5'} entries</h2>
          <div className="auto-box">
            <div className="auto-head">
              <strong>
                {autoInfo?.decision?.day || '—'} · {autoInfo?.decision?.slot || '—'}
              </strong>
              <span className={`side ${autoInfo?.decision?.allow_trading ? 'buy' : 'sell'}`}>
                {autoInfo?.decision?.allow_trading ? 'LIVE' : 'FLAT'}
              </span>
            </div>
            <p className="auto-reason">
              {autoInfo?.decision?.reason || 'Waiting for auto decision…'}
            </p>
            <div className="meta">
              Regime: {autoInfo?.decision?.regime || '—'} · Using:{' '}
              <code>{autoInfo?.display || autoInfo?.active_strategy || '—'}</code>
              {autoInfo?.decision?.adx != null
                ? ` · ADX ${Number(autoInfo.decision.adx).toFixed(1)}`
                : ''}
            </div>
            <div className="entry-rules">
              <strong>Kailan papasok</strong>
              <ul>
                {(desk?.entry_rules || []).map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </div>
            {(desk?.entry_checklist || []).length > 0 ? (
              <ul className="entry-checklist">
                {desk.entry_checklist.map((c) => (
                  <li key={c.name} className={c.ok ? 'ok' : 'fail'}>
                    <span>{c.ok ? '✓' : '✗'}</span> {c.name}: {c.detail}
                  </li>
                ))}
              </ul>
            ) : null}
            <ul className="auto-schedule">
              {(autoInfo?.schedule || []).map((row) => (
                <li key={`${row.slot}-${row.utc}`}>
                  <span>
                    {row.days} {row.utc}
                  </span>
                  <span>
                    <strong>{row.slot}</strong> — {row.strategies}
                  </span>
                </li>
              ))}
            </ul>
            {desk?.last_block_reason ? (
              <div className="meta" style={{ color: '#ffb4b4', marginTop: '0.65rem' }}>
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
                  <th>Stop Loss</th>
                  <th>Take Profit</th>
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
                    <td>{p.stop_loss ?? '—'}</td>
                    <td>{p.take_profit ?? '—'}</td>
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

        <section className="panel" style={{ gridColumn: '1 / -1' }}>
          <div className="chart-head">
            <h2>Trade log</h2>
            <span className="meta">
              {tradeSummary
                ? `${tradeSummary.closed} closed · ${tradeSummary.wins}W/${tradeSummary.losses}L · net $${money(tradeSummary.net_pnl)}`
                : 'entry · SL · TP · exit'}
            </span>
          </div>
          {trades.length === 0 ? (
            <div className="empty">No trades yet — waiting for signals/fills.</div>
          ) : (
            <div className="trade-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Status</th>
                    <th>Side</th>
                    <th>Lots</th>
                    <th>Entry</th>
                    <th>Stop Loss</th>
                    <th>Take Profit</th>
                    <th>Exit</th>
                    <th>P&amp;L</th>
                    <th>Reason</th>
                    <th>Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.id || t.ticket}>
                      <td className="meta">
                        {t.opened_at ? new Date(t.opened_at).toLocaleString() : '—'}
                      </td>
                      <td>
                        <span
                          className={`side ${
                            t.status === 'CLOSED'
                              ? t.realized_pnl >= 0
                                ? 'buy'
                                : 'sell'
                              : t.status === 'OPEN'
                                ? 'buy'
                                : 'sell'
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td>
                        <span className={`side ${(t.side || '').toLowerCase()}`}>{t.side}</span>
                      </td>
                      <td>{t.lots}</td>
                      <td>{t.entry ?? '—'}</td>
                      <td>{t.stop_loss ?? '—'}</td>
                      <td>{t.take_profit ?? '—'}</td>
                      <td>{t.exit ?? '—'}</td>
                      <td
                        className={pnlClass(
                          t.status === 'OPEN' ? t.unrealized_pnl : t.realized_pnl,
                        )}
                      >
                        $
                        {money(
                          t.status === 'OPEN' ? t.unrealized_pnl : t.realized_pnl,
                        )}
                      </td>
                      <td className="meta">
                        {t.close_reason || t.reject_reason || t.comment || '—'}
                      </td>
                      <td className="meta">{t.strategy || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
