import { useEffect, useRef, useState } from 'react'
import { api, connectFeed, ensureAccountSession, saveAccountSession } from './api'
import CandleChart from './CandleChart'
import TradingViewGoldChart from './TradingViewGoldChart'
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

/** Map engine labels back to select value (clean slate = manual_only). */
function normalizeStrategy(label) {
  if (!label) return 'manual_only'
  if (label === 'auto' || label.startsWith('auto_gold')) return 'manual_only'
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
  const [aiAdvice, setAiAdvice] = useState(null)
  const [aiStatus, setAiStatus] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [strategy, setStrategy] = useState('manual_only')
  const [appliedStrategy, setAppliedStrategy] = useState('manual_only')
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
  const [chartMode, setChartMode] = useState(() => {
    try {
      const saved = localStorage.getItem('jm_chart_mode')
      // Default desk tape — shows EMA + signal arrows + Entry/SL/TP lines
      return saved === 'desk' || saved === 'tradingview' ? saved : 'desk'
    } catch {
      return 'desk'
    }
  }) // tradingview | desk
  const [depositInput, setDepositInput] = useState('1000')
  const [capital, setCapital] = useState(null)
  const [accountMeta, setAccountMeta] = useState(null)
  const [loginCode, setLoginCode] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [showAccountLogin, setShowAccountLogin] = useState(false)
  const accountIdRef = useRef(null)

  useEffect(() => {
    let alive = true
    let disconnect = () => {}

    const applySignals = (list) => {
      if (!alive || !Array.isArray(list)) return
      setSignals(list.slice(0, 40))
    }

    const onFeed = (msg) => {
      if (!alive) return
      const myId = accountIdRef.current
      const dataAid = msg.data?.account_id
      if (
        dataAid &&
        myId &&
        dataAid !== myId &&
        ['account', 'positions', 'trades', 'trade', 'order', 'position', 'position_closed'].includes(
          msg.event,
        )
      ) {
        return
      }
      if (msg.event === 'engine') {
        setStatus(msg.data)
        if (msg.data?.mode) setMode(msg.data.mode)
        if (msg.data?.active_strategy) syncStrategyFromServer(msg.data.active_strategy)
      }
      if (msg.event === 'account') setAccount(msg.data)
      if (msg.event === 'positions') {
        const list = Array.isArray(msg.data) ? msg.data : msg.data?.positions || []
        setPositions(list)
      }
      if (msg.event === 'tick') {
        setTicks((prev) => ({ ...prev, [msg.data.symbol]: msg.data }))
      }
      // Desk-wide: snapshot + live ticks — never account-filtered
      if (msg.event === 'signals') {
        applySignals(msg.data?.signals || [])
      }
      if (msg.event === 'signal') {
        setSignals((prev) => {
          const row = msg.data
          if (!row) return prev
          const key = `${row.timestamp}|${row.side}|${row.strategy}|${row.reason || ''}`
          const rest = prev.filter(
            (s) => `${s.timestamp}|${s.side}|${s.strategy}|${s.reason || ''}` !== key,
          )
          return [row, ...rest].slice(0, 40)
        })
      }
      if (msg.event === 'ai_advice') {
        setAiAdvice(msg.data)
      }
      if (msg.event === 'ai') {
        setAiStatus(msg.data)
        if (msg.data?.last_advice) setAiAdvice(msg.data.last_advice)
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
        setLiveCandle(null)
        setCandles((prev) => {
          const next = [
            ...prev.filter(
              (c) =>
                (c.open_time || c.timestamp) !== (msg.data.open_time || msg.data.timestamp),
            ),
          ]
          next.push(msg.data)
          return next.slice(-240)
        })
      }
      if (msg.event === 'trades') {
        setTrades(msg.data?.trades || [])
        setTradeSummary(msg.data?.summary || null)
      }
      if (msg.event === 'trade') {
        setTrades((prev) => {
          const rest = prev.filter((t) => t.id !== msg.data.id && t.ticket !== msg.data.ticket)
          return [msg.data, ...rest].slice(0, 100)
        })
      }
      if (msg.event === 'auto') setAutoInfo(msg.data)
      if (msg.event === 'transfer') {
        setAutoInfo((prev) => ({
          ...(prev || {}),
          last_transfer: `${msg.data.from_slot} → ${msg.data.to_slot}: ${msg.data.strategy}`,
          session_slot: msg.data.to_slot,
        }))
      }
    }

    ;(async () => {
      // 1) Desk-wide tape first — signals/candles must work even if account auth fails
      //    (different browsers create different paper accounts; signals are shared).
      try {
        const deskResults = await Promise.allSettled([
          api.status(),
          api.signals(),
          api.ticks(),
          api.strategies(),
          api.desk(),
          api.mtStatus(),
          api.candles('XAUUSD', 200),
          api.auto(),
        ])
        if (!alive) return
        const val = (i) =>
          deskResults[i].status === 'fulfilled' ? deskResults[i].value : null
        const st = val(0)
        const sig = val(1)
        const tk = val(2)
        const strat = val(3)
        const deskInfo = val(4)
        const mtInfo = val(5)
        const candleInfo = val(6)
        const auto = val(7)
        if (st) {
          setStatus(st)
          setMode(st.mode || st.connection?.mode || 'paper')
          clearStrategyDirty(st.active_strategy)
        }
        if (sig) applySignals(sig.signals || [])
        if (strat) setStrategies(strat.strategies || [])
        if (deskInfo) {
          setDesk(deskInfo)
          if (deskInfo.ai) setAiStatus(deskInfo.ai)
        }
        if (mtInfo) setMt(mtInfo)
        if (auto) setAutoInfo(auto)
        if (candleInfo) setCandles(candleInfo.candles || [])
        if (tk) {
          const map = {}
          for (const t of tk.ticks || []) map[t.symbol] = t
          setTicks(map)
        }
        const deskErr = deskResults.find((r) => r.status === 'rejected')
        if (deskErr && !st) {
          setError(deskErr.reason?.message || 'Failed to load desk API')
        }
      } catch (err) {
        if (alive) setError(err.message || 'Failed to load desk API')
      }

      // 2) Private paper book for this browser (capital / positions / fills)
      try {
        const session = await ensureAccountSession({ deposit: 1000, label: 'Client demo' })
        if (!alive) return
        accountIdRef.current = session.id
        setAccountMeta({
          id: session.id,
          code: session.code,
          label: session.label,
        })
        const bookResults = await Promise.allSettled([
          api.account(),
          api.positions(),
          api.trades(100),
          api.aiAdvice().catch(() => null),
        ])
        if (!alive) return
        const bval = (i) =>
          bookResults[i].status === 'fulfilled' ? bookResults[i].value : null
        const acc = bval(0)
        const pos = bval(1)
        const tradeInfo = bval(2)
        const advice = bval(3)
        if (acc) {
          setAccount(acc)
          setCapital(acc.capital || null)
          if (acc.deposit != null) setDepositInput(String(acc.deposit))
          else if (acc.capital?.deposit != null) setDepositInput(String(acc.capital.deposit))
        }
        if (pos) setPositions(pos.open || [])
        if (tradeInfo) {
          setTrades(tradeInfo.trades || [])
          setTradeSummary(tradeInfo.summary || null)
        }
        if (advice?.advice) setAiAdvice(advice.advice)
        if (advice?.status) setAiStatus(advice.status)
      } catch (err) {
        if (alive) {
          setError((prev) => prev || err.message || 'Failed to load paper account')
        }
      }

      if (!alive) return
      disconnect = connectFeed(onFeed)
    })()

    const deskTimer = setInterval(() => {
      api.desk().then((d) => alive && setDesk(d)).catch(() => {})
      api.mtStatus().then((m) => alive && setMt(m)).catch(() => {})
      // Refresh shared signal tape so other browsers stay in sync even if a WS event was missed
      api
        .signals()
        .then((sig) => alive && applySignals(sig.signals || []))
        .catch(() => {})
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

  async function signInPaperAccount(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.loginAccount(loginCode.trim(), loginPassword)
      saveAccountSession({
        id: res.account_id,
        token: res.token,
        code: res.account_code,
        label: res.account_label,
      })
      window.location.reload()
    } catch (err) {
      setError(err.message || 'Invalid account code or password')
    } finally {
      setBusy(false)
    }
  }

  async function autoTransferBySession() {
    await run(async () => {
      const res = await api.autoTransfer()
      if (res?.message) setOrderNote(res.message)
      return res
    })
  }

  async function applyDeposit(amount) {
    const value = Number(amount ?? depositInput)
    if (!Number.isFinite(value) || value < 50) {
      setError('Minimum paper deposit is $50')
      return
    }
    await run(async () => {
      const res = await api.setDeposit(value, true)
      if (res?.account) setAccount(res.account)
      if (res?.capital) setCapital(res.capital)
      setDepositInput(String(res?.capital?.deposit ?? value))
      if (res?.trades?.trades) setTrades(res.trades.trades)
      if (res?.trades?.summary) setTradeSummary(res.trades.summary)
      else {
        const tradeInfo = await api.trades(100)
        setTrades(tradeInfo.trades || [])
        setTradeSummary(tradeInfo.summary || null)
      }
      const pos = await api.positions()
      setPositions(pos.open || [])
      setOrderNote(res?.message || `Paper deposit set to $${value}`)
      return res
    })
  }

  async function previewDeposit(amount) {
    try {
      const preview = await api.capitalPreview(amount)
      setCapital(preview)
    } catch (err) {
      setError(err.message || 'Preview failed')
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
          XAUUSD scalp desk — EMA+RSI momentum or SMC liquidity sweep.
          Manual Buy/Sell with auto SL/TP anytime.
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
                  'AI_ML',
                  'manual_only',
                  'EMA_RSI_Scalp',
                  'Liquidity_Sweep_SMC',
                  'London_Judas_Sweep',
                  'EMA_VWAP_Scalp',
                ]
            ).map((name) => (
              <option key={name} value={name}>
                {name === 'AI_ML'
                  ? 'AI_ML (AI & Machine Learning stack)'
                  : name === 'manual_only'
                    ? 'manual_only (no auto signals)'
                    : name === 'EMA_RSI_Scalp'
                      ? 'EMA_RSI_Scalp (EMA200 + RSI + pin/engulf)'
                      : name === 'Liquidity_Sweep_SMC'
                        ? 'Liquidity_Sweep_SMC (sweep + FVG/OB)'
                        : name === 'London_Judas_Sweep'
                          ? 'London_Judas_Sweep (Asia trap · FVG50 limit · 07-11 UTC)'
                          : name === 'EMA_VWAP_Scalp'
                            ? 'EMA_VWAP_Scalp (9/21 EMA + VWAP)'
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
            onClick={() => autoTransferBySession()}
            title="Auto follow by session time"
          >
            Auto transfer (session)
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
              Strategies: AI_ML · London_Judas · EMA_RSI · SMC · VWAP · manual
            </span>
            <span className="meta">
              {(desk?.recommended_now || autoInfo?.recommended)?.reason ||
                'Pick a strategy and Apply'}
            </span>
            {autoInfo?.last_transfer ? (
              <span className="meta">Note: {autoInfo.last_transfer}</span>
            ) : null}
          </div>
          )
        })()}
      </header>

      <section className="metrics" aria-label="Account metrics">
        <div className="metric">
          <label>Demo acct</label>
          <strong>{accountMeta?.code || account.account_code || '—'}</strong>
        </div>
        <div className="metric">
          <label>Equity</label>
          <strong>${money(account.equity)}</strong>
        </div>
        <div className="metric">
          <label>Balance</label>
          <strong>${money(account.balance)}</strong>
        </div>
        <div className="metric">
          <label>Deposit</label>
          <strong>${money(account.deposit ?? capital?.deposit ?? account.balance)}</strong>
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

      {(() => {
        const fill = autoInfo?.auto_fill || desk?.auto?.auto_fill
        const myCode = (accountMeta?.code || account.account_code || '').toUpperCase()
        if (!fill || !myCode) return null
        const targets = fill.targets || (fill.target ? [fill.target] : [])
        const inFanOut = !fill.single_book
        const isTarget = targets.some((t) => (t.code || '').toUpperCase() === myCode)
        if (inFanOut) {
          return (
            <section className="panel auto-fill-active" aria-label="Auto fill routing">
              <p className="meta">
                <strong>Centralized desk</strong> — one signal for all accounts. Auto fills
                go to <strong>{fill.followers ?? targets.length}</strong> follow_auto book
                {fill.followers === 1 ? '' : 's'} including <strong>{myCode}</strong>.
              </p>
            </section>
          )
        }
        const targetCode = (fill.target?.code || '').toUpperCase()
        const isSingleTarget = targetCode && myCode === targetCode
        return (
          <section
            className={`panel ${isSingleTarget ? 'auto-fill-active' : 'auto-fill-warn'}`}
            aria-label="Auto fill routing"
          >
            {isSingleTarget ? (
              <p className="meta">
                <strong>Auto fills active</strong> — signals open trades on{' '}
                <strong>{myCode}</strong> (this account). Keep this tab open during sessions.
              </p>
            ) : fill.target ? (
              <p className="meta">
                <strong>Signals only on this account</strong> — auto fills go to account{' '}
                <strong>{targetCode}</strong>
                {fill.selection === 'connected'
                  ? ' (another browser is connected). '
                  : ' (older server account). '}
                Refresh with this tab open, or clear site data and reload.
              </p>
            ) : (
              <p className="meta">
                <strong>No auto-fill target</strong> — reload the desk so your demo account
                connects; trades will not copy from signals until then.
              </p>
            )}
          </section>
        )
      })()}

      <section className="panel deposit-panel" aria-label="Paper deposit">
        <div className="deposit-head">
          <div>
            <h2>Paper deposit · private trial capital</h2>
            <p className="meta">
              This browser has its own demo account ({accountMeta?.code || '…'}). Other clients
              cannot see your capital, open trades, or history. Trade log is kept when you
              change deposit; open positions close into the log.
            </p>
            <p className="meta">
              <button
                type="button"
                className="linkish"
                onClick={() => setShowAccountLogin((v) => !v)}
              >
                {showAccountLogin ? 'Hide sign-in' : 'Sign in to existing account (code + password)'}
              </button>
            </p>
            {showAccountLogin ? (
              <form className="account-login-form" onSubmit={signInPaperAccount}>
                <label>
                  Account code
                  <input
                    value={loginCode}
                    onChange={(e) => setLoginCode(e.target.value.toUpperCase())}
                    placeholder="3295D7"
                    autoComplete="username"
                  />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="demo12345"
                    autoComplete="current-password"
                  />
                </label>
                <button type="submit" className="btn primary" disabled={busy}>
                  Sign in
                </button>
              </form>
            ) : null}
          </div>
          <span className={`badge ${account.paper !== false && mode === 'paper' ? 'badge-live' : ''}`}>
            {mode === 'paper' ? 'PAPER DEMO' : 'LIVE MT'}
          </span>
        </div>

        <div className="deposit-presets">
          {(capital?.presets || [100, 250, 500, 1000, 2500, 5000, 10000]).map((p) => (
            <button
              key={p}
              type="button"
              className={`preset-btn ${Number(depositInput) === p ? 'on' : ''}`}
              disabled={busy || mode !== 'paper'}
              onClick={() => {
                setDepositInput(String(p))
                previewDeposit(p)
              }}
            >
              ${p.toLocaleString()}
            </button>
          ))}
        </div>

        <div className="deposit-controls">
          <label className="lots-field">
            Deposit (USD)
            <input
              type="number"
              min="50"
              max="1000000"
              step="50"
              value={depositInput}
              disabled={busy || mode !== 'paper'}
              onChange={(e) => {
                setDepositInput(e.target.value)
                const n = Number(e.target.value)
                if (Number.isFinite(n) && n >= 50) previewDeposit(n)
              }}
            />
          </label>
          <button
            type="button"
            className="primary"
            disabled={busy || mode !== 'paper'}
            onClick={() => applyDeposit()}
          >
            Set deposit
          </button>
        </div>

        {capital ? (
          <div className="capital-calc" aria-label="Capital calculation">
            <div>
              <label>Risk / trade</label>
              <strong>
                ${money(capital.risk_per_trade_usd)}{' '}
                <span className="meta">({capital.risk_per_trade_pct}%)</span>
              </strong>
            </div>
            <div>
              <label>Max daily loss</label>
              <strong>
                {capital.daily_loss_limit_enabled === false ||
                Number(capital.max_daily_loss_pct) <= 0
                  ? 'Off'
                  : `$${money(capital.max_daily_loss_usd)}`}{' '}
                <span className="meta">
                  {capital.daily_loss_limit_enabled === false ||
                  Number(capital.max_daily_loss_pct) <= 0
                    ? '(disabled)'
                    : `(${capital.max_daily_loss_pct}%)`}
                </span>
              </strong>
            </div>
            <div>
              <label>Suggested lots</label>
              <strong>
                {Number(capital.suggested_lots).toFixed(2)}{' '}
                <span className="meta">
                  SL {capital.default_stop_loss_pips}p / TP {capital.default_take_profit_pips}p
                </span>
              </strong>
            </div>
          </div>
        ) : null}
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
        <div className="chart-mode-bar">
          <button
            type="button"
            className={`chart-mode-btn ${chartMode === 'tradingview' ? 'on' : ''}`}
            onClick={() => {
              setChartMode('tradingview')
              try {
                localStorage.setItem('jm_chart_mode', 'tradingview')
              } catch {
                /* ignore */
              }
            }}
          >
            Live gold
          </button>
          <button
            type="button"
            className={`chart-mode-btn ${chartMode === 'desk' ? 'on' : ''}`}
            onClick={() => {
              setChartMode('desk')
              try {
                localStorage.setItem('jm_chart_mode', 'desk')
              } catch {
                /* ignore */
              }
            }}
          >
            Desk tape ({mode})
          </button>
          <span className="meta chart-mode-hint">
            {chartMode === 'tradingview'
              ? 'Live COMEX gold candles · strategies still use paper/MT feed'
              : 'Desk tape — Live · M5 · M15 · H1 · 1M Daily · EMA/RSI/SL/TP'}
          </span>
        </div>
        {chartMode === 'tradingview' ? (
          <TradingViewGoldChart symbol="TVC:GOLD" interval="5" />
        ) : (
          <CandleChart
            candles={candles}
            liveCandle={liveCandle}
            livePrice={gold?.mid}
            symbol="XAUUSD"
            positions={positions}
            signals={signals}
          />
        )}
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
          <h2>Desk signals</h2>
          <p className="meta" style={{ marginTop: 0 }}>
            Shared desk tape — same BUY/SELL list on every browser. Paper fills stay on
            this account ({accountMeta?.code || '…'}) only.
          </p>
          <div className="signal-list">
            {signals.length === 0 ? (
              <div className="empty">Waiting for confluence signals…</div>
            ) : (
              signals.map((s, i) => {
                const side = String(s.side?.value || s.side || '').toUpperCase()
                return (
                  <div className="signal" key={`${s.timestamp}-${side}-${s.strategy}-${i}`}>
                    <span className={`side ${side.toLowerCase()}`}>{side || '—'}</span>
                    <div>
                      <div>
                        <strong>{s.symbol}</strong> · {s.strategy}
                      </div>
                      <div className="meta">{s.reason}</div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </section>

        <section className="panel" style={{ gridColumn: '1 / -1' }}>
          <div className="chart-head">
            <h2>AI &amp; Machine Learning</h2>
            <span className="meta">
              {aiStatus?.history?.labeled != null
                ? `${aiStatus.history.labeled} labeled · ${aiStatus.model?.algorithm || 'ML'} · n=${aiStatus.model?.samples_seen ?? 0}`
                : 'scikit-learn model · learns from closed SL/TP history'}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const res = await api.aiRetrain()
                  setAiStatus(res.status || res)
                  const advice = await api.aiAdvice()
                  if (advice?.advice) setAiAdvice(advice.advice)
                  if (advice?.status) setAiStatus(advice.status)
                  setOrderNote(
                    `AI & ML retrain · ${res.retrained_on ?? 0} samples` +
                      (res.ingested_from_journal
                        ? ` · +${res.ingested_from_journal} from journal`
                        : ''),
                  )
                  return res
                })
              }
            >
              Retrain
            </button>
          </div>
          {!aiAdvice ? (
            <div className="empty">Waiting for a signal to score…</div>
          ) : (
            <div className={`ai-box action-${(aiAdvice.action || '').toLowerCase()}`}>
              <div className="auto-head">
                <strong>
                  {aiAdvice.action} · win p={Math.round((aiAdvice.win_probability || 0) * 100)}%
                </strong>
                <span className={`side ${aiAdvice.action === 'TAKE' ? 'buy' : 'sell'}`}>
                  {aiAdvice.gated ? 'GATED' : aiAdvice.action}
                </span>
              </div>
              <p className="auto-reason">
                {(aiAdvice.reasons && aiAdvice.reasons[0]) ||
                  'AI & Machine Learning score ready'}
              </p>
              <div className="meta">
                {aiAdvice.source || 'AI & Machine Learning'} · confidence{' '}
                {Math.round((aiAdvice.confidence || 0) * 100)}% · session{' '}
                {aiAdvice.context?.session || '—'} ·{' '}
                {aiAdvice.context?.soft_confirm ? 'soft confirm' : 'hard confirm'}
                {aiAdvice.context?.rsi != null ? ` · RSI ${aiAdvice.context.rsi}` : ''}
              </div>
              {(aiAdvice.reasons || []).length > 1 ? (
                <ul className="ai-reasons">
                  {aiAdvice.reasons.slice(1).map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
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
            <button
              type="button"
              disabled={busy || trades.length === 0}
              onClick={() =>
                run(async () => {
                  const res = await api.clearTrades()
                  setTrades(res.trades?.trades || [])
                  setTradeSummary(res.trades?.summary || null)
                  setPositions([])
                  if (res.account) setAccount(res.account)
                  setOrderNote(res.message || 'Trade log cleared')
                  return res
                })
              }
            >
              Clear log
            </button>
          </div>
          {trades.length === 0 ? (
            <div className="empty">
              No fills on this paper account yet. Desk signals are shared — when auto is on,
              the same TAKE/CAUTION signal opens a trade on every follow_auto account.
            </div>
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
        · paper / MT4 / MT5 · live candles · AI_ML + EMA_RSI + SMC
      </p>
    </div>
  )
}
