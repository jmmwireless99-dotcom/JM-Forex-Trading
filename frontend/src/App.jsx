import { useEffect, useRef, useState } from 'react'
import AccountAuth from './AccountAuth'
import AccountProfile from './AccountProfile'
import {
  api,
  clearAccountSession,
  connectFeed,
  loadAccountSession,
  restoreAccountSession,
  saveAccountSession,
} from './api'
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
    asia: 'Asia (UTC 00–07 / PH 8AM–3PM)',
    london: 'London (UTC 07–11 / PH 3–7PM)',
    london_wind_down: 'London wind-down · EMA (UTC 11–12)',
    london_close: 'London close · EMA + kill (UTC 12–13)',
    london_ny_overlap: 'London/NY overlap (UTC 13–16 / PH 9PM–12AM)',
    new_york: 'New York (UTC 16–20 / PH 12–4AM)',
    friday_late: 'Friday late',
    weekend: 'Weekend',
    off_hours: 'Off-hours · EMA (UTC 20–24 / PH 4–8AM)',
    outside_asia_desk: 'Outside Asia desk',
    asia_off: 'Asia / off',
    hourly: 'Hourly auto-transfer',
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
      return saved === 'desk' || saved === 'tradingview' ? saved : 'tradingview'
    } catch {
      return 'tradingview'
    }
  }) // tradingview | desk
  const [depositInput, setDepositInput] = useState('1000')
  const [capital, setCapital] = useState(null)
  const [accountMeta, setAccountMeta] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [sessionBoot, setSessionBoot] = useState(0)
  const [authTab, setAuthTab] = useState('login')
  const accountIdRef = useRef(null)

  useEffect(() => {
    let alive = true
    let disconnect = () => {}
    ;(async () => {
      try {
        const session = await restoreAccountSession()
        if (!alive) return
        if (!session) {
          setAccountMeta(null)
          accountIdRef.current = null
          setAuthReady(true)
          return
        }
        accountIdRef.current = session.id
        setAccountMeta({
          id: session.id,
          code: session.code,
          label: session.label,
          avatar: session.avatar || session.account?.avatar || '',
          has_password: Boolean(session.account?.has_password),
        })
        setAuthReady(true)

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
        setCapital(acc.capital || null)
        if (acc.deposit != null) setDepositInput(String(acc.deposit))
        else if (acc.capital?.deposit != null) setDepositInput(String(acc.capital.deposit))
        if (acc.fixed_lots != null) setManualLots(String(acc.fixed_lots))
        setAccountMeta((prev) => ({
          ...(prev || {}),
          id: acc.account_id || prev?.id,
          code: acc.account_code || prev?.code,
          label: acc.account_label || prev?.label,
          avatar: acc.avatar || prev?.avatar || '',
          has_password: Boolean(acc.has_password),
          mt_platform: acc.mt_platform || prev?.mt_platform || null,
          mt5_login: acc.mt5_login || prev?.mt5_login || null,
          binding: acc.binding || prev?.binding || null,
          preferred_strategy: acc.preferred_strategy || prev?.preferred_strategy || null,
        }))
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
        // Restore saved strategy (manual select/save) on login/boot.
        const pref = acc.preferred_strategy
          ? normalizeStrategy(acc.preferred_strategy)
          : null
        if (pref && normalizeStrategy(st.active_strategy) !== pref) {
          try {
            await api.setStrategy(pref)
            clearStrategyDirty(pref)
            setOrderNote(`Restored saved strategy: ${pref}`)
          } catch {
            markStrategyChoice(pref)
          }
        } else {
          clearStrategyDirty(pref || st.active_strategy)
        }
        const map = {}
        for (const t of tk.ticks || []) map[t.symbol] = t
        setTicks(map)

        disconnect = connectFeed((msg) => {
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
          if (msg.event === 'account') {
            setAccount(msg.data)
            setAccountMeta((prev) => ({
              ...(prev || {}),
              mt_platform: msg.data?.mt_platform ?? prev?.mt_platform ?? null,
              mt5_login: msg.data?.mt5_login ?? prev?.mt5_login ?? null,
              binding: msg.data?.binding ?? prev?.binding ?? null,
              label: msg.data?.account_label || prev?.label,
              code: msg.data?.account_code || prev?.code,
            }))
          }
          if (msg.event === 'positions') {
            const list = Array.isArray(msg.data)
              ? msg.data
              : msg.data?.positions || []
            setPositions(list)
          }
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
            const sym = msg.data?.symbol || msg.data?.candles?.[0]?.symbol
            if (!sym || sym === 'XAUUSD') {
              setCandles(msg.data.candles || [])
            }
          }
          if (msg.event === 'candle') {
            if (msg.data?.symbol && msg.data.symbol !== 'XAUUSD') return
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
            if (msg.data?.symbol && msg.data.symbol !== 'XAUUSD') return
            setLiveCandle(null)
            setCandles((prev) => {
              const next = [...prev.filter((c) => (c.open_time || c.timestamp) !== (msg.data.open_time || msg.data.timestamp))]
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
        })
      } catch (err) {
        if (alive) {
          setAuthReady(true)
          setError(err.message || 'Failed to load API')
        }
      }
    })()

    const deskTimer = setInterval(() => {
      if (!accountIdRef.current) return
      api.desk().then((d) => alive && setDesk(d)).catch(() => {})
      api.mtStatus().then((m) => alive && setMt(m)).catch(() => {})
    }, 10000)

    return () => {
      alive = false
      disconnect()
      clearInterval(deskTimer)
    }
  }, [sessionBoot])

  function handleAuthed(session) {
    setError('')
    setAccountMeta({
      id: session.id,
      code: session.code,
      label: session.label,
      avatar: session.avatar || '',
      has_password: Boolean(session.account?.has_password ?? true),
      mt_platform: session.account?.mt_platform || null,
      mt5_login: session.account?.mt5_login || null,
      binding: session.account?.binding || null,
    })
    accountIdRef.current = session.id
    setAuthReady(true)
    setSessionBoot((n) => n + 1)
  }

  function endSession(nextTab = 'login') {
    try {
      clearAccountSession()
    } catch {
      /* ignore */
    }
    accountIdRef.current = null
    setAccountMeta(null)
    setAccount(emptyAccount)
    setPositions([])
    setTrades([])
    setTradeSummary(null)
    setCapital(null)
    setError('')
    setOrderNote('')
    setAuthTab(nextTab)
    setAuthReady(true)
    setSessionBoot((n) => n + 1)
  }

  function handleLogout() {
    endSession('login')
  }

  function handleSwitchAccount() {
    endSession('login')
  }

  function handleProfileUpdated(next) {
    setAccountMeta((prev) => {
      const merged = { ...(prev || {}), ...next }
      const existing = loadAccountSession()
      if (existing?.token) {
        saveAccountSession({
          id: merged.id || existing.id,
          token: existing.token,
          code: merged.code || existing.code,
          label: merged.label || existing.label,
          avatar: merged.avatar || '',
        })
      }
      return merged
    })
  }

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
    await run(async () => {
      const res = await api.setStrategy(strategy)
      // Manual select + save preferred strategy on this account
      try {
        const saved = await api.setTradeSettings({ preferred_strategy: strategy })
        if (saved?.account) setAccount((prev) => ({ ...prev, ...saved.account }))
      } catch {
        /* save is best-effort if guest/desk */
      }
      setOrderNote(
        res?.message ||
          `Strategy set to ${strategy} (saved · session auto-follow OFF)`,
      )
      return res
    })
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
  const accountPlatform = String(account?.mt_platform || accountMeta?.mt_platform || '').toLowerCase()
  const accountBinding = account?.binding || accountMeta?.binding || ''
  const myPlatOnline = accountPlatform === 'mt4' || accountPlatform === 'mt5'
    ? Boolean(mt?.platforms?.[accountPlatform]?.online)
    : mtOnline
  const gold = ticks.XAUUSD
  const quoteTick = gold
  const maxOpen = Number(desk?.risk?.max_open_positions) || 3
  const hasOpen = positions.length > 0
  const chartPositions = positions.filter(
    (p) => !p.symbol || p.symbol === 'XAUUSD',
  )
  const atMaxOpen = positions.length >= maxOpen
  const hasBuyOpen = chartPositions.some((p) => p.side === 'BUY')
  const hasSellOpen = chartPositions.some((p) => p.side === 'SELL')

  if (!authReady) {
    return (
      <div className="app">
        <div className="auth-screen">
          <div className="auth-card">
            <p className="meta">Loading account…</p>
          </div>
        </div>
      </div>
    )
  }

  if (!accountMeta?.id) {
    return (
      <div className="app">
        <AccountAuth key={authTab} initialTab={authTab} onAuthed={handleAuthed} />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="hero">
        <div className="brand-lockup">
          <h1 className="brand">
            JM <span>Forex</span>
          </h1>
          <div className="mode-chip">
            {status?.running ? 'Desk live' : 'Paused'}
            {accountPlatform === 'mt4' || accountPlatform === 'mt5'
              ? ` · Your ${accountPlatform.toUpperCase()}${
                  accountBinding === `live_${accountPlatform}`
                    ? myPlatOnline
                      ? ' · bound'
                      : ' · waiting agent'
                    : accountBinding === 'waiting_mt'
                      ? ' · waiting agent'
                      : ''
                }`
              : ` · ${mode.toUpperCase()}${
                  mode !== 'paper' ? (mtOnline ? ' · MT online' : ' · MT offline') : ''
                }`}
          </div>
          <AccountProfile
            meta={accountMeta}
            onUpdated={handleProfileUpdated}
            onLogout={handleLogout}
            onSwitchAccount={handleSwitchAccount}
          />
        </div>
        <p>
          XAUUSD scalp desk. Manual select → Apply/Save. Buy/Sell with auto SL/TP anytime.
        </p>
        <div className="controls">
          {accountPlatform === 'mt4' || accountPlatform === 'mt5' ? (
            <span className="meta" title="Per-account live platform — change in Profile">
              Account: <strong>{accountPlatform.toUpperCase()}</strong>
              {accountBinding ? ` (${accountBinding})` : ''} — Profile → Live platform
            </span>
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
                  'manual_only',
                  'EMA_RSI_Scalp',
                  'London_Judas_Sweep',
                  'Liquidity_Sweep_SMC',
                ]
            ).map((name) => (
              <option key={name} value={name}>
                {name === 'manual_only'
                  ? 'manual_only (no auto signals)'
                  : name === 'EMA_RSI_Scalp'
                    ? 'EMA_RSI_Scalp (XAU · EMA200 + RSI · Asia/NY)'
                    : name === 'London_Judas_Sweep'
                      ? 'London_Judas_Sweep (XAU · Asia sweep → FVG · London)'
                      : name === 'Liquidity_Sweep_SMC'
                        ? 'Liquidity_Sweep_SMC (XAU · PDH/PDL sweep → FVG50 · overlap)'
                        : name}
              </option>
            ))}
          </select>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() => applyStrategy()}
            title="Lock + save preferred strategy; turn OFF gold session auto-follow"
          >
            Apply & save strategy
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() => autoTransferBySession()}
            title="Auto follow by session — also re-checks every UTC hour by itself"
          >
            Auto transfer (hourly)
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
              Auto schedule (hourly, always-on): Asia/NY/off EMA · London Judas · Overlap SMC
            </span>
            <span className="meta">
              {(desk?.recommended_now || autoInfo?.recommended)?.reason ||
                'Pick a strategy and Apply'}
            </span>
            {autoInfo?.last_transfer ? (
              <span className="meta">Note: {autoInfo.last_transfer}</span>
            ) : null}
            {autoInfo?.hourly_transfer ? (
              <span className="meta">
                Hourly auto-transfer ON
                {autoInfo.next_hourly_transfer_in_seconds != null
                  ? ` · next check ~${Math.max(1, Math.ceil(autoInfo.next_hourly_transfer_in_seconds / 60))}m`
                  : ''}
              </span>
            ) : null}
          </div>
          )
        })()}
      </header>

      <section className="metrics" aria-label="Account metrics">
        <div className="metric">
          <label>Demo acct</label>
          <strong>{accountMeta?.code || account.account_code || '—'}</strong>
          <span className="meta">{accountMeta?.label || account.account_label || ''}</span>
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

      <section className="panel deposit-panel" aria-label="Paper deposit">
        <div className="deposit-head">
          <div>
            <h2>Paper deposit · private trial capital</h2>
            <p className="meta">
              Signed in as {accountMeta?.label || 'Demo'} ({accountMeta?.code || '…'}). Other
              clients cannot see your capital, open trades, or history. Logout / switch account
              keeps your trade log. Deposit changes keep history; open positions close into the
              log.
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

      <section className="manual-trade" aria-label="Manual buy sell">
        <div className="manual-trade-head">
          <strong>Manual trade</strong>
          <span className="meta">
            XAUUSD · lots {manualLots} ·{' '}
            {autoStops ? 'Auto SL/TP ON' : 'No SL/TP on fill'}
          </span>
        </div>
        <div className="manual-prices">
          <div className="price-pill sell">
            <label>SELL</label>
            <strong>
              {quoteTick?.bid != null ? Number(quoteTick.bid).toFixed(2) : '—'}
            </strong>
          </div>
          <div className="price-pill mid">
            <label>MID</label>
            <strong>
              {quoteTick?.mid != null ? Number(quoteTick.mid).toFixed(2) : '—'}
            </strong>
          </div>
          <div className="price-pill buy">
            <label>BUY</label>
            <strong>
              {quoteTick?.ask != null ? Number(quoteTick.ask).toFixed(2) : '—'}
            </strong>
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
            disabled={busy || !quoteTick || atMaxOpen || hasBuyOpen}
            onClick={() => manualTrade('SELL')}
            title={
              hasBuyOpen
                ? 'BUY still open — no opposite flip'
                : atMaxOpen
                  ? `Max ${maxOpen} open positions`
                  : 'Market SELL XAUUSD'
            }
          >
            SELL {quoteTick?.bid != null ? Number(quoteTick.bid).toFixed(2) : ''}
          </button>
          <button
            type="button"
            className="btn-buy"
            disabled={busy || !quoteTick || atMaxOpen || hasSellOpen}
            onClick={() => manualTrade('BUY')}
            title={
              hasSellOpen
                ? 'SELL still open — no opposite flip'
                : atMaxOpen
                  ? `Max ${maxOpen} open positions`
                  : 'Market BUY XAUUSD'
            }
          >
            BUY {quoteTick?.ask != null ? Number(quoteTick.ask).toFixed(2) : ''}
          </button>
        </div>
        {orderNote ? <div className="meta manual-note">{orderNote}</div> : null}
        {hasOpen ? (
          <div className="meta">
            Open {positions.length}/{maxOpen}
            {atMaxOpen
              ? ' — max reached. Close one to add another.'
              : ' — same-direction adds OK when signal is clear; no opposite flip.'}
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
            Live market
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
              ? 'Live COMEX gold · strategies still use paper/MT feed'
              : 'Engine XAUUSD candles — paper sim or MT bridge'}
            {quoteTick ? ` · mid ${quoteTick.mid}` : ''}
          </span>
        </div>
        {chartMode === 'tradingview' ? (
          <TradingViewGoldChart interval="5" />
        ) : (
          <CandleChart
            candles={candles}
            liveCandle={liveCandle}
            symbol="XAUUSD"
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
            <button
              type="button"
              disabled={busy || trades.length === 0}
              onClick={() =>
                run(async () => {
                  const ok = window.confirm(
                    'Clear trade log for THIS account only? This cannot be undone.',
                  )
                  if (!ok) return null
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
          <h2>Scalp desk · Entry rules</h2>
          <div className="strategy-card-grid">
            {(desk?.strategy_details || []).map((strat) => {
              const active =
                status?.active_strategy === strat.id ||
                autoInfo?.active_strategy === strat.id
              const scheduleMatch = (autoInfo?.schedule || []).find((row) =>
                (strat.sessions || []).some(
                  (s) =>
                    row.slot?.toLowerCase().includes(s.toLowerCase().split('/')[0]) ||
                    row.strategies?.includes(strat.id),
                ),
              )
              return (
                <article
                  key={strat.id}
                  className={`strategy-card${active ? ' strategy-card-active' : ''}`}
                >
                  <header className="strategy-card-head">
                    <div>
                      <h3>{strat.name}</h3>
                      <p className="strategy-card-summary">{strat.summary}</p>
                    </div>
                    <div className="strategy-card-badges">
                      {active ? <span className="badge badge-live">ACTIVE</span> : null}
                      <span className="badge">{strat.order_type}</span>
                      {strat.reward_r ? (
                        <span className="badge">{strat.reward_r}R target</span>
                      ) : null}
                    </div>
                  </header>

                  <div className="strategy-card-meta">
                    <span>
                      <strong>Sessions</strong> {strat.sessions?.join(' · ') || '—'}
                    </span>
                    <span>
                      <strong>TF</strong> {strat.chart_tf} chart · {strat.signal_tf} signal
                    </span>
                    {scheduleMatch ? (
                      <span>
                        <strong>Window</strong> {scheduleMatch.utc} UTC
                      </span>
                    ) : null}
                  </div>

                  <div className="strategy-card-section">
                    <strong>Entry rules</strong>
                    <ul>
                      {(strat.entry_rules || []).map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                  </div>

                  {strat.entry_flow?.length ? (
                    <div className="strategy-card-section">
                      <strong>Flow</strong>
                      <ol>
                        {strat.entry_flow.map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ol>
                    </div>
                  ) : null}

                  {strat.parameters && Object.keys(strat.parameters).length ? (
                    <div className="strategy-card-params">
                      {Object.entries(strat.parameters).map(([key, val]) => (
                        <span key={key}>
                          <code>{key}</code>{' '}
                          {Array.isArray(val) ? val.join(', ') : String(val)}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {strat.safety?.length ? (
                    <div className="strategy-card-safety">
                      <strong>Safety</strong>
                      <ul>
                        {strat.safety.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>

          <div className="entry-rules entry-rules-compact">
            <strong>
              Session schedule (Mon–Fri) · strategy auto-transfer every UTC hour
            </strong>
            <ul className="auto-schedule">
              {(autoInfo?.schedule || []).map((row) => (
                <li key={`${row.slot}-${row.utc}`}>
                  <span>
                    {row.days} UTC {row.utc}
                    {row.ph ? ` · PH ${row.ph}` : ''}
                  </span>
                  <span>
                    <strong>{row.slot}</strong> — {row.strategies}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>

      <p className="footer-note">
        Part of{' '}
        <a href="https://jmtechsolution.cloud" style={{ color: '#7dffb3' }}>
          JM TECH SOLUTION
        </a>
        {' '}
        · paper / MT4 / MT5 · live candles · EMA_RSI + SMC
      </p>
    </div>
  )
}
