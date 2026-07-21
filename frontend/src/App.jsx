import { useEffect, useRef, useState } from 'react'
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

/** Map engine label like "auto_gold→gold_atr_trend" back to select value. */
function normalizeStrategy(label) {
  if (!label) return 'auto_gold'
  if (label === 'auto' || label.startsWith('auto_gold')) return 'auto_gold'
  return label
}

function sessionLabel(raw) {
  const key = String(raw || '').toLowerCase()
  const map = {
    asia: 'Asia (PH 7AM–5PM)',
    london: 'London',
    london_ny_overlap: 'London / NY overlap',
    new_york: 'New York',
    friday_late: 'Friday late',
    weekend: 'Weekend',
    off_hours: 'Off-hours',
    outside_asia_desk: 'Outside Asia desk',
    asia_off: 'Asia / off',
  }
  return map[key] || (raw ? String(raw).replace(/_/g, ' ') : '—')
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
  const [appliedStrategy, setAppliedStrategy] = useState('auto_gold')
  const [strategyDirty, setStrategyDirty] = useState(false)
  const strategyDirtyRef = useRef(false)
  const [mode, setMode] = useState('paper')
  const [autoInfo, setAutoInfo] = useState(null)

  function markStrategyChoice(name) {
    setStrategy(name)
    setStrategyDirty(true)
    strategyDirtyRef.current = true
  }

  function syncStrategyFromServer(label) {
    const live = normalizeStrategy(label)
    setAppliedStrategy(live)
    if (!strategyDirtyRef.current) {
      setStrategy(live)
    }
  }

  function clearStrategyDirty(label) {
    const live = normalizeStrategy(label)
    setStrategy(live)
    setAppliedStrategy(live)
    setStrategyDirty(false)
    strategyDirtyRef.current = false
  }
  const [candles, setCandles] = useState([])
  const [liveCandle, setLiveCandle] = useState(null)
  const [trades, setTrades] = useState([])
  const [tradeSummary, setTradeSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [manualLots, setManualLots] = useState(0.01)
  const [autoStops, setAutoStops] = useState(true)
  const [orderNote, setOrderNote] = useState('')

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
        clearStrategyDirty(st.active_strategy)
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
        if (msg.data?.active_strategy) syncStrategyFromServer(msg.data.active_strategy)
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
        // Do not overwrite the strategy <select> here — Apply/engine status owns that.
      }
      if (msg.event === 'transfer') {
        setAutoInfo((prev) => ({
          ...(prev || {}),
          last_transfer: `${msg.data.from_slot} → ${msg.data.to_slot}: ${msg.data.strategy}`,
          session_slot: msg.data.to_slot,
        }))
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
      if (next?.running !== undefined || next?.mode || next?.active_strategy) setStatus(next)
      if (next?.status) setStatus(next.status)
      if (next?.auto) setAutoInfo(next.auto)
      else {
        try {
          setAutoInfo(await api.auto())
        } catch {
          /* ignore */
        }
      }
      if (next?.active_strategy) clearStrategyDirty(next.active_strategy)
      else if (next?.selected) clearStrategyDirty(next.selected)
      setDesk(await api.desk())
      setMt(await api.mtStatus())
    } catch (err) {
      setError(err.message || 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function applyStrategy() {
    await run(async () => api.setStrategy(strategy))
  }

  async function autoTransfer() {
    await run(async () => {
      const result = await api.autoTransfer()
      if (result?.to) clearStrategyDirty('auto_gold')
      return result
    })
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

  async function manualTrade(side) {
    await run(async () => {
      const order = await api.placeOrder({
        symbol: 'XAUUSD',
        side,
        lots: Number(manualLots) || 0.01,
        comment: 'manual',
        auto_stops: autoStops,
      })
      if (order?.status === 'REJECTED') {
        throw new Error(order.reject_reason || 'Order rejected')
      }
      const sl = order.stop_loss != null ? ` SL ${order.stop_loss}` : ''
      const tp = order.take_profit != null ? ` TP ${order.take_profit}` : ''
      setOrderNote(
        `${order.side} ${order.lots} @ ${order.fill_price ?? '—'}${sl}${tp}`,
      )
      const pos = await api.positions()
      setPositions(pos.open || [])
      setAccount(await api.account())
      const tradeInfo = await api.trades(100)
      setTrades(tradeInfo.trades || [])
      setTradeSummary(tradeInfo.summary || null)
      return null
    })
  }

  async function attachAutoStops(id) {
    await run(async () => {
      await api.setStops(id, { auto: true })
      const pos = await api.positions()
      setPositions(pos.open || [])
      setOrderNote('Auto SL/TP attached')
      return null
    })
  }

  const sessionTier = desk?.session?.tier || '—'
  const newsBlocked = Boolean(desk?.news?.blocked)
  const mtOnline = Boolean(mt?.online || mt?.mt_online)
  const gold = ticks.XAUUSD
  const hasOpen = positions.length > 0

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
            onChange={(e) => markStrategyChoice(e.target.value)}
            disabled={busy}
          >
            {(strategies.length
              ? strategies
              : [
                  'auto_gold',
                  'asia_m5_sr_scalp',
                  'asia_m3m5_sr_scalp',
                  'asia_sr_scalp',
                  'gold_confluence',
                  'gold_atr_trend',
                  'gold_sr_scalp',
                  'asia_range_scalp',
                  'ema_crossover',
                  'rsi_mean_reversion',
                ]
            ).map((name) => (
              <option key={name} value={name}>
                {name === 'auto_gold'
                  ? 'auto_gold (session follow)'
                  : name === 'asia_m5_sr_scalp'
                    ? 'asia_m5_sr_scalp (BEST Asia · M5 S/R · 7AM–5PM)'
                    : name === 'asia_m3m5_sr_scalp'
                      ? 'asia_m3m5_sr_scalp (Asia M3 entry / M5 S/R)'
                      : name === 'asia_sr_scalp'
                        ? 'asia_sr_scalp (Asia M5 S/R legacy)'
                        : name === 'gold_confluence'
                          ? 'gold_confluence (BEST London)'
                          : name === 'gold_atr_trend'
                            ? 'gold_atr_trend (BEST overlap/NY)'
                            : name === 'asia_range_scalp'
                              ? 'asia_range_scalp (Asia Donchian)'
                              : name === 'gold_sr_scalp'
                                ? 'gold_sr_scalp (S/R chop)'
                                : name}
              </option>
            ))}
          </select>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() => applyStrategy()}
            title="Apply selected strategy without restarting"
          >
            Apply strategy
          </button>
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() => autoTransfer()}
            title="ON = Auto follow: Asia M5 S/R (7AM–5PM) → London → Overlap/NY"
          >
            Auto transfer
          </button>
          <button
            className="btn-ghost"
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
          <span>
            Strategy: {status?.active_strategy || autoInfo?.display || '—'}
            {strategyDirty ? ` · selected ${strategy} (not applied)` : ''}
          </span>
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
        {(desk?.recommended_now || autoInfo?.recommended) && (() => {
          const rec = desk?.recommended_now || autoInfo?.recommended || {}
          const activeSession =
            autoInfo?.session_slot ||
            autoInfo?.decision?.slot ||
            rec.session ||
            desk?.session?.label
          const activeStrat =
            (status?.active_strategy || '').includes('→')
              ? status.active_strategy.split('→')[1]
              : status?.active_strategy ||
                rec.transfer_to ||
                rec.strategy ||
                autoInfo?.active_strategy ||
                '—'
          return (
          <div className="recommend-box">
            <strong>Active session</strong>
            <span>
              {sessionLabel(activeSession)} ·{' '}
              <code>{activeStrat}</code>
            </span>
            <span className="meta">
              BEST now:{' '}
              <code>
                {(desk?.recommended_now || autoInfo?.recommended)?.strategy ||
                  activeStrat}
              </code>
            </span>
            {(() => {
              const nxt =
                (desk?.recommended_now || autoInfo?.recommended)?.next_session ||
                desk?.next_session
              if (!nxt?.strategy) return null
              return (
                <span className="meta">
                  Next session ({sessionLabel(nxt.session)}):{' '}
                  <code>{nxt.strategy}</code>
                </span>
              )
            })()}
            <span className="meta">
              {(desk?.recommended_now || autoInfo?.recommended)?.reason || ''}
            </span>
            {autoInfo?.last_transfer ? (
              <span className="meta">Last transfer: {autoInfo.last_transfer}</span>
            ) : null}
            <span className="meta">
              Active now: {sessionLabel(activeSession)} session
              {autoInfo?.enabled
                ? ` · following with ${activeStrat}`
                : ' · auto follow OFF'}
            </span>
            {!autoInfo?.enabled ? (
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                onClick={() => autoTransfer()}
              >
                I-ON ang Auto transfer (session follow)
              </button>
            ) : (
              <span className="mode-chip">
                Auto ON · {sessionLabel(activeSession)}
              </span>
            )}
          </div>
          )
        })()}
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

      <section className="manual-trade" aria-label="Manual buy sell">
        <div className="manual-trade-head">
          <strong>Manual trade</strong>
          <span className="meta">
            XAUUSD · {autoStops ? 'Auto SL/TP ON' : 'No SL/TP on fill'}
          </span>
        </div>
        <div className="manual-prices">
          <div className="price-pill sell">
            <label>SELL</label>
            <strong>{gold?.bid != null ? Number(gold.bid).toFixed(2) : '—'}</strong>
          </div>
          <div className="price-pill mid">
            <label>MID</label>
            <strong>{gold?.mid != null ? Number(gold.mid).toFixed(2) : '—'}</strong>
          </div>
          <div className="price-pill buy">
            <label>BUY</label>
            <strong>{gold?.ask != null ? Number(gold.ask).toFixed(2) : '—'}</strong>
          </div>
        </div>
        <div className="manual-controls">
          <label className="lots-field">
            Lots
            <input
              type="number"
              min="0.01"
              max="10"
              step="0.01"
              value={manualLots}
              disabled={busy}
              onChange={(e) => setManualLots(e.target.value)}
            />
          </label>
          <label className="auto-stops-toggle">
            <input
              type="checkbox"
              checked={autoStops}
              disabled={busy}
              onChange={(e) => setAutoStops(e.target.checked)}
            />
            Auto SL/TP after fill
          </label>
          <button
            type="button"
            className="btn-sell"
            disabled={busy || !gold || hasOpen}
            onClick={() => manualTrade('SELL')}
            title={hasOpen ? 'Close open position first' : 'Market SELL'}
          >
            SELL {gold?.bid != null ? Number(gold.bid).toFixed(2) : ''}
          </button>
          <button
            type="button"
            className="btn-buy"
            disabled={busy || !gold || hasOpen}
            onClick={() => manualTrade('BUY')}
            title={hasOpen ? 'Close open position first' : 'Market BUY'}
          >
            BUY {gold?.ask != null ? Number(gold.ask).toFixed(2) : ''}
          </button>
        </div>
        {orderNote ? <div className="meta manual-note">{orderNote}</div> : null}
        {hasOpen ? (
          <div className="meta">
            Flat first (1 position max) — Close open trade, or attach Auto SL/TP below.
          </div>
        ) : null}
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
            {desk?.asia_range ? (
              <div className="meta" style={{ marginTop: '0.55rem' }}>
                Asia range: {desk.asia_range.low} – {desk.asia_range.high} · mid{' '}
                {desk.asia_range.mid} · ADX {desk.asia_range.adx}
              </div>
            ) : null}
            {(desk?.entry_checklist || []).length > 0 ? (
              <ul className="entry-checklist">
                {desk.entry_checklist.map((c) => (
                  <li key={c.name} className={c.ok ? 'ok' : 'fail'}>
                    <span>{c.ok ? '✓' : '✗'}</span> {c.name}: {c.detail}
                  </li>
                ))}
              </ul>
            ) : null}
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
                    <td className="pos-actions">
                      {p.stop_loss == null || p.take_profit == null ? (
                        <button
                          className="btn-ghost"
                          disabled={busy}
                          onClick={() => attachAutoStops(p.id)}
                          title="Auto attach desk default SL/TP"
                        >
                          Auto SL/TP
                        </button>
                      ) : null}
                      <button
                        className="btn-ghost"
                        disabled={busy}
                        onClick={() => onClose(p.id)}
                      >
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

        <section className="panel schedule-bottom" style={{ gridColumn: '1 / -1' }}>
          <h2>Kailan papasok · Weekly schedule</h2>
          <div className="entry-rules">
            <strong>Entry rules</strong>
            <ul>
              {(desk?.entry_rules || []).map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          </div>
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
