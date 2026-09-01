import { useEffect, useRef, useState } from 'react'
import { api, connectFeed, loadAccountSession, logoutAccount, saveAccountSession } from './api'
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
    asia: 'Asia (PH 7AM–8PM)',
    london: 'London',
    london_ny_overlap: 'SMC (PH 8PM–2AM)',
    new_york: 'New York',
    friday_late: 'Friday late',
    weekend: 'Weekend',
    off_hours: 'Early Asia (PH 2AM–7AM)',
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
  const [mt4Bridge, setMt4Bridge] = useState(null)
  const mt5Only = Boolean(account?.mt5_only || accountMeta?.mt5?.mt5_only)
  const mt4Real = Boolean(
    account?.mt4_real ||
      (account?.mt4_only && account?.account_kind === 'real') ||
      accountMeta?.mt4?.mt4_real ||
      accountMeta?.mt5?.mt4_real ||
      accountMeta?.mt5?.platform === 'mt4_real',
  )
  const mtLinkedOnly = mt5Only || mt4Real
  const scaleInMode = Boolean(account?.scale_in_mode || accountMeta?.scale_in_mode)
  const mt4RealRef = useRef(false)
  const mtLinkedOnlyRef = useRef(false)
  const [authState, setAuthState] = useState('loading') // loading | in | out
  const [showLoginPanel, setShowLoginPanel] = useState(false)
  const [loginCode, setLoginCode] = useState('')
  const [loginToken, setLoginToken] = useState('')
  const accountIdRef = useRef(null)

  async function loadAccountBook(session) {
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
    const bval = (i) => (bookResults[i].status === 'fulfilled' ? bookResults[i].value : null)
    const acc = bval(0)
    const pos = bval(1)
    const tradeInfo = bval(2)
    const advice = bval(3)
    if (acc) {
      setAccount(acc)
      setCapital(acc.capital || null)
      if (acc.mt5_only) {
        setAccountMeta((prev) => ({
          ...(prev || {}),
          code: acc.account_code || session.code,
          label: acc.account_label || session.label,
          mt5: { mt5_only: true, mt5_login: acc.mt5_login, linked: acc.mt5_linked },
        }))
      } else if (acc.mt4_real || acc.mt4_only) {
        setAccountMeta((prev) => ({
          ...(prev || {}),
          code: acc.account_code || session.code,
          label: acc.account_label || session.label,
          mt4: {
            mt4_real: true,
            mt4_login: acc.mt4_real_login,
            linked: acc.mt4_real_linked,
            platform: acc.mt_platform || 'mt4_real',
            symbol: acc.mt4_symbol || 'GOLD',
          },
        }))
        setMode('mt4')
        api.mt4Status().then(setMt4Bridge).catch(() => {})
      }
      if (!acc.mt5_only && !acc.mt4_real && !acc.mt4_only) {
        if (acc.deposit != null) setDepositInput(String(acc.deposit))
        else if (acc.capital?.deposit != null) setDepositInput(String(acc.capital.deposit))
      }
    }
    if (pos) setPositions(pos.open || [])
    if (tradeInfo) {
      setTrades(tradeInfo.trades || [])
      setTradeSummary(tradeInfo.summary || null)
    }
    if (advice?.advice) setAiAdvice(advice.advice)
    if (advice?.status) setAiStatus(advice.status)
    setAuthState('in')
    setShowLoginPanel(false)
  }

  async function handleLogin(e) {
    e?.preventDefault?.()
    setBusy(true)
    setError('')
    try {
      const res = await api.loginAccount({ code: loginCode, token: loginToken })
      const session = {
        id: res.account_id,
        token: loginToken.trim(),
        code: res.account_code,
        label: res.account_label,
      }
      const isMt4Real = Boolean(res.mt5?.mt4_real || res.mt5?.platform === 'mt4_real')
      setAccountMeta({
        code: res.account_code,
        label: res.account_label,
        mt5: res.mt5?.mt5_only ? res.mt5 : null,
        mt4: isMt4Real ? res.mt5 : null,
      })
      if (isMt4Real) {
        setMode('mt4')
        api.mt4Status().then(setMt4Bridge).catch(() => {})
      }
      saveAccountSession(session)
      await loadAccountBook(session)
      setLoginCode('')
      setLoginToken('')
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  function handleLogout() {
    logoutAccount()
    setAuthState('out')
    setShowLoginPanel(true)
    setAccountMeta(null)
    setAccount(emptyAccount)
    setPositions([])
    setTrades([])
    setTradeSummary(null)
    accountIdRef.current = null
  }

  async function handleCreateScaleInDemoAccount() {
    setBusy(true)
    setError('')
    try {
      const created = await api.createScaleInAccount({
        deposit: 1000,
        label: 'Scale-in demo (3 legs)',
      })
      const session = {
        id: created.account.account_id,
        token: created.token,
        code: created.account.account_code,
        label: created.account.account_label,
      }
      saveAccountSession(session)
      await loadAccountBook(session)
    } catch (err) {
      setError(err.message || 'Could not create scale-in account')
    } finally {
      setBusy(false)
    }
  }

  async function handleCreateDemoAccount() {
    setBusy(true)
    setError('')
    try {
      const created = await api.createAccount({ deposit: 1000, label: 'Client demo', follow_auto: true })
      const session = {
        id: created.account.account_id,
        token: created.token,
        code: created.account.account_code,
        label: created.account.account_label,
      }
      saveAccountSession(session)
      await loadAccountBook(session)
    } catch (err) {
      setError(err.message || 'Could not create account')
    } finally {
      setBusy(false)
    }
  }

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
        if (msg.data?.mode && !mtLinkedOnlyRef.current) setMode(msg.data.mode)
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
        if (msg.data?.mode && !mtLinkedOnlyRef.current) setMode(msg.data.mode)
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
          if (!mtLinkedOnlyRef.current) {
            setMode(st.mode || st.connection?.mode || 'paper')
          }
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
        const session = loadAccountSession()
        if (!session) {
          if (alive) {
            setAuthState('out')
            setShowLoginPanel(true)
          }
        } else {
          try {
            await loadAccountBook(session)
          } catch {
            logoutAccount()
            if (alive) {
              setAuthState('out')
              setShowLoginPanel(true)
            }
          }
        }
      } catch (err) {
        if (alive) {
          setError((prev) => prev || err.message || 'Failed to load paper account')
          setAuthState('out')
          setShowLoginPanel(true)
        }
      }

      if (!alive) return
      disconnect = connectFeed(onFeed)
    })()

    const deskTimer = setInterval(() => {
      api.desk().then((d) => alive && setDesk(d)).catch(() => {})
      if (mt4RealRef.current) {
        api.mt4Status().then((m) => alive && setMt4Bridge(m)).catch(() => {})
      } else {
        api.mtStatus().then((m) => alive && setMt(m)).catch(() => {})
      }
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

  useEffect(() => {
    mt4RealRef.current = mt4Real
    mtLinkedOnlyRef.current = mtLinkedOnly
  }, [mt4Real, mtLinkedOnly])

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
  const newsInfo = desk?.news || {}
  const newsBlocked = Boolean(newsInfo.blocked)
  const newsArmed = Boolean(newsInfo.news_strategy_armed)
  const newsEntryOpen = Boolean(newsInfo.trading_window_active)
  const ffCalendar = newsInfo.forex_factory || {}
  const ffEvents = ffCalendar.events_today || []
  const ffFetchedAt = ffCalendar.fetched_at
  const mtOnline = Boolean(mt?.online || mt?.mt_online)
  const mt4Online = Boolean(mt4Bridge?.online)
  const mtLinkedOnline = mt5Only ? mtOnline : mt4Real ? mt4Online : mtOnline
  const mtLinkedLabel = mt5Only ? 'MT5 LIVE' : mt4Real ? 'MT4 LIVE' : mode.toUpperCase()
  const mt4Linked = Boolean(
    account.mt4_real_linked || accountMeta?.mt4?.linked || accountMeta?.mt5?.linked,
  )
  const gold = ticks.XAUUSD
  const goldLabel = mt5Only ? 'GOLD#' : 'XAUUSD'
  const mt4Symbol = accountMeta?.mt4?.symbol || mt4Bridge?.symbol || 'GOLD'
  const hasOpen = positions.length > 0

  return (
    <div className="app">
      <header className="hero">
        <div className="brand-lockup">
          <h1 className="brand">
            JM <span>Forex</span>
          </h1>
          <div className="mode-chip">
            {status?.running ? 'Desk live' : 'Paused'} · {mtLinkedLabel}
            {mtLinkedOnly ? (
              mtLinkedOnline ? ' · Sync OK' : ' · Sync offline'
            ) : scaleInMode ? (
              ' · Scale-in 3L'
            ) : mode !== 'paper' ? (
              mtOnline ? ' · MT online' : ' · MT offline'
            ) : (
              ''
            )}
          </div>
          {authState === 'in' && accountMeta ? (
            <div className="account-session-bar">
              <span className="meta">
                Signed in · <strong>{accountMeta.code}</strong>
                {accountMeta.label ? ` · ${accountMeta.label}` : ''}
              </span>
              <button
                type="button"
                className="btn-ghost account-session-btn"
                disabled={busy}
                onClick={() => setShowLoginPanel(true)}
              >
                Switch account
              </button>
              <button
                type="button"
                className="btn-ghost account-session-btn"
                disabled={busy}
                onClick={handleLogout}
              >
                Log out
              </button>
            </div>
          ) : null}
        </div>
        <p>
          XAUUSD scalp desk — EMA+RSI momentum or SMC liquidity sweep.
          Manual Buy/Sell with auto SL/TP anytime.
        </p>
        <div className="controls">
          {mtLinkedOnly ? (
            <>
              {mt5Only ? (
                <>
                  <span className="badge badge-live" style={{ alignSelf: 'center' }}>
                    MT5 · {account.mt5_login || '169250320'} · GOLD#
                  </span>
                  <span className="meta" style={{ alignSelf: 'center' }}>
                    {account.mt5_linked && mtOnline
                      ? 'Balance synced from XM terminal'
                      : 'Waiting for PC Agent + MT5 bridge'}
                  </span>
                </>
              ) : (
                <>
                  <span className="badge badge-live" style={{ alignSelf: 'center' }}>
                    MT4 · {account.mt4_real_login || accountMeta?.mt4?.mt4_login || accountMeta?.mt4?.login || 'live'} · {mt4Symbol}
                  </span>
                  <span className="meta" style={{ alignSelf: 'center' }}>
                    {mt4Linked && mt4Online
                      ? 'Balance synced from XM MT4 live terminal'
                      : 'Waiting for JM_Forex_Bridge EA on MT4'}
                  </span>
                </>
              )}
            </>
          ) : (
            <>
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
            </>
          )}
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
          <span>
            News:{' '}
            {newsArmed
              ? newsEntryOpen
                ? 'NewsBreakout LIVE'
                : 'NewsBreakout armed'
              : newsBlocked
                ? 'BLACKOUT'
                : 'clear'}
          </span>
          <span>
            MT:{' '}
            {mtLinkedOnly
              ? mtLinkedOnline
                ? 'online'
                : 'offline'
              : mtOnline
                ? 'online'
                : mt?.configured || mt?.mt_configured
                  ? 'offline'
                  : 'not configured'}
            {mt5Only ? (
              accountMeta?.mt5?.tick_ok || gold?.bid > 0
                ? ' · tick OK'
                : ' · tick waiting (set InpSymbol=GOLD#)'
            ) : mt4Real ? (
              mt4Bridge?.tick?.bid > 0 || gold?.bid > 0
                ? ' · tick OK'
                : ' · tick waiting (set InpSymbol=GOLD on MT4 chart)'
            ) : null}
          </span>
          {mt5Only ? (
            <span>
              Sync: {account.mt5_linked && mtOnline ? 'OK · $' + Number(account.balance || 0).toFixed(2) : 'offline'}
            </span>
          ) : mt4Real ? (
            <span>
              Sync: {mt4Linked && mt4Online ? 'OK · $' + Number(account.balance || 0).toFixed(2) : 'offline'}
            </span>
          ) : null}
          {gold ? <span>{goldLabel} {gold.mid}</span> : null}
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
              Strategies: AI_ML · EMA_RSI · SMC · VWAP · manual
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

      {(showLoginPanel || authState === 'out') && (
        <section className="panel account-auth-panel" aria-label="Account login">
          <h2>{authState === 'in' ? 'Switch account' : 'Sign in to your JM FX account'}</h2>
          <p className="meta">
            Use your <strong>account code</strong> + <strong>token</strong> to open your private
            trade log. Log out anytime to switch accounts (e.g. XM MT5 Demo).
          </p>
          <form className="account-auth-form" onSubmit={handleLogin}>
            <label>
              Account code
              <input
                type="text"
                value={loginCode}
                onChange={(e) => setLoginCode(e.target.value.toUpperCase())}
                placeholder="e.g. DDDC3D"
                autoComplete="username"
                disabled={busy}
              />
            </label>
            <label>
              Token
              <input
                type="password"
                value={loginToken}
                onChange={(e) => setLoginToken(e.target.value)}
                placeholder="Paste your account token"
                autoComplete="current-password"
                disabled={busy}
              />
            </label>
            <div className="account-auth-actions">
              <button type="submit" className="btn-primary" disabled={busy || !loginCode || !loginToken}>
                Sign in
              </button>
              {authState === 'in' ? (
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={busy}
                  onClick={() => setShowLoginPanel(false)}
                >
                  Cancel
                </button>
              ) : null}
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                onClick={handleCreateScaleInDemoAccount}
              >
                Create scale-in demo (3 legs)
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                onClick={handleCreateDemoAccount}
              >
                Create new demo account
              </button>
            </div>
          </form>
        </section>
      )}

      {authState === 'in' ? (
      <>
      <section className="metrics" aria-label="Account metrics">
        <div className="metric">
          <label>{mt5Only ? 'MT5 acct' : mt4Real ? 'MT4 acct' : scaleInMode ? 'Scale-in acct' : 'Demo acct'}</label>
          <strong>{accountMeta?.code || account.account_code || '—'}</strong>
          {scaleInMode ? (
            <span className="badge badge-live" style={{ display: 'block', marginTop: '0.35rem' }}>
              3-leg scale-in · 0.01/0.02/0.03 per $1k
            </span>
          ) : null}
          {accountMeta?.label ? (
            <span className="meta" style={{ display: 'block', marginTop: '0.2rem' }}>
              {accountMeta.label}
            </span>
          ) : null}
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

        {!mtLinkedOnly ? (
      <section className="panel deposit-panel" aria-label="Paper deposit">
        <div className="deposit-head">
          <div>
            <h2>Paper deposit · private trial capital</h2>
            <p className="meta">
              This browser has its own demo account ({accountMeta?.code || '…'}). Other clients
              cannot see your capital, open trades, or history. Trade log is kept when you
              change deposit; open positions close into the log.
            </p>
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
      ) : mt5Only ? (
      <section className="panel deposit-panel" aria-label="MT5 account">
        <div className="deposit-head">
          <div>
            <h2>XM MT5 live account</h2>
            <p className="meta">
              <strong>{accountMeta?.code || account.account_code}</strong> uses your XM MT5 demo
              balance only — no paper money. Login <strong>{account.mt5_login || accountMeta?.mt5?.mt5_login || '169250320'}</strong>
              · symbol <strong>{accountMeta?.mt5?.symbol || 'GOLD#'}</strong>.
              Keep MT5 open with JM_Forex_Bridge on the GOLD# chart.
            </p>
          </div>
          <span className="badge badge-live">MT5 LIVE</span>
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
      ) : (
      <section className="panel deposit-panel" aria-label="MT4 account">
        <div className="deposit-head">
          <div>
            <h2>XM MT4 live account</h2>
            <p className="meta">
              <strong>{accountMeta?.code || account.account_code}</strong> uses your XM MT4 live
              balance only — no paper money. Login{' '}
              <strong>
                {account.mt4_real_login ||
                  accountMeta?.mt4?.mt4_login ||
                  accountMeta?.mt4?.login ||
                  '—'}
              </strong>
              · symbol <strong>{mt4Symbol}</strong>.
              Keep MT4 open with JM_Forex_Bridge EA v2 (cloud bridge) on the {mt4Symbol} chart.
            </p>
          </div>
          <span className="badge badge-live">MT4 LIVE</span>
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
      )}

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
            Desk tape ({mt5Only ? 'MT5' : mt4Real ? 'MT4' : mode})
          </button>
          <span className="meta chart-mode-hint">
            {chartMode === 'tradingview'
              ? 'Live COMEX gold candles · strategies still use paper/MT feed'
              : mt5Only
                ? 'GOLD# desk tape — synced from XM MT5 · M5 · M15 · H1 · 1M Daily'
                : mt4Real
                  ? `${mt4Symbol} desk tape — synced from XM MT4 live · M5 · M15 · H1 · 1M Daily`
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
            symbol={goldLabel}
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

        <section className="panel news-panel" style={{ gridColumn: '1 / -1' }}>
          <h2>News calendar · NewsBreakout</h2>
          <div
            className={`news-box${newsArmed ? ' armed' : ''}${newsEntryOpen ? ' entry-live' : ''}${newsBlocked ? ' blackout' : ''}`}
          >
            <div className="auto-head">
              <strong>
                {newsInfo.scheduled_event || (newsInfo.news_day ? 'News day' : 'No high-impact news today')}
              </strong>
              <span className={`side ${newsArmed ? (newsEntryOpen ? 'buy' : 'sell') : 'sell'}`}>
                {newsArmed
                  ? newsEntryOpen
                    ? 'ENTRY OPEN'
                    : 'ARMED'
                  : newsInfo.news_day
                    ? 'WAITING'
                    : 'OFF'}
              </span>
            </div>
            <p className="auto-reason">
              {newsInfo.news_strategy_reason ||
                newsInfo.reason ||
                'NFP · CPI · FOMC · Core PCE — auto NewsBreakout PH 7PM–7AM, T-60m before release'}
            </p>
            <div className="news-grid meta">
              <span>
                Release (PH):{' '}
                {newsInfo.scheduled_release_utc
                  ? new Date(newsInfo.scheduled_release_utc).toLocaleString('en-PH', {
                      timeZone: 'Asia/Manila',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      hour12: true,
                    })
                  : '—'}
              </span>
              <span>
                EMA_RSI blackout:{' '}
                <strong>{newsBlocked ? 'ON (stand aside)' : 'clear'}</strong>
                {newsInfo.event ? ` · ${newsInfo.event}` : ''}
              </span>
              <span>
                NewsBreakout auto:{' '}
                <strong>{newsInfo.news_breakout_auto === false ? 'disabled' : 'enabled'}</strong>
              </span>
              <span>
                Entry window:{' '}
                <strong>
                  {newsEntryOpen
                    ? 'post-spike (+5 to +60m)'
                    : newsArmed
                      ? 'armed — wait for release'
                      : 'closed'}
                </strong>
              </span>
            </div>
            {newsInfo.trading_window_reason ? (
              <div className="meta" style={{ marginTop: '0.55rem' }}>
                {newsInfo.trading_window_reason}
              </div>
            ) : null}
          </div>

          <div className="news-ff-head meta">
            <span>
              Source:{' '}
              <a
                href={ffCalendar.source_url || 'https://www.forexfactory.com/calendar'}
                target="_blank"
                rel="noreferrer"
              >
                Forex Factory
              </a>
              {ffCalendar.enabled === false ? ' (proxy fallback)' : ' · live feed'}
            </span>
            <span>
              Updated:{' '}
              {ffFetchedAt
                ? new Date(ffFetchedAt).toLocaleTimeString('en-PH', {
                    timeZone: 'Asia/Manila',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: true,
                  })
                : '—'}
            </span>
          </div>

          {ffCalendar.last_error ? (
            <div className="meta news-ff-error">Feed: {ffCalendar.last_error}</div>
          ) : null}

          <div className="news-ff-scroll">
            <table className="table news-ff-table">
              <thead>
                <tr>
                  <th>Time (PH)</th>
                  <th>CCY</th>
                  <th>Impact</th>
                  <th>Event</th>
                  <th>Actual</th>
                  <th>Forecast</th>
                  <th>Previous</th>
                </tr>
              </thead>
              <tbody>
                {ffEvents.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="meta">
                      Loading Forex Factory calendar…
                    </td>
                  </tr>
                ) : (
                  ffEvents.map((ev) => {
                    const phTime = new Date(ev.when_utc).toLocaleString('en-PH', {
                      timeZone: 'Asia/Manila',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      hour12: true,
                    })
                    const impact = (ev.impact || 'Low').toLowerCase()
                    const rowClass = [
                      ev.imminent ? 'news-ff-imminent' : '',
                      ev.is_past ? 'news-ff-past' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')
                    const countdown =
                      ev.minutes_until > 0
                        ? `in ${ev.minutes_until}m`
                        : ev.minutes_until < 0
                          ? `${Math.abs(ev.minutes_until)}m ago`
                          : 'now'
                    return (
                      <tr key={`${ev.when_utc}-${ev.title}-${ev.country}`} className={rowClass}>
                        <td>
                          {phTime}
                          <div className="meta news-ff-countdown">{countdown}</div>
                        </td>
                        <td>{ev.country}</td>
                        <td>
                          <span className={`news-impact news-impact-${impact}`}>
                            {ev.impact}
                          </span>
                        </td>
                        <td>{ev.title}</td>
                        <td>{ev.actual || '—'}</td>
                        <td>{ev.forecast || '—'}</td>
                        <td>{ev.previous || '—'}</td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

      </div>
      </>
      ) : null}

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
