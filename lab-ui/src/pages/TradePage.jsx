import { useCallback, useEffect, useMemo, useState } from 'react'
import LabCandleChart from '../LabCandleChart.jsx'
import { PAIR_GUIDE, PAIR_PRESETS, STRATEGY_INFO } from '../content/compare.js'
import { labTradeApi, loadLabSession, saveLabSession, ensurePairAccount, setLabSessionPair } from '../api.js'
import { PAIR_URL_SYMBOLS, pairTradePath } from '../routing.js'

const PAIRS = PAIR_GUIDE.filter((p) => p.status === 'live' || p.status === 'live-ref').map((p) => p.id)

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

export default function TradePage({ fixedPair = null }) {
  const lockedPair = fixedPair ? String(fixedPair).toUpperCase() : null

  const [session, setSession] = useState(() => loadLabSession(lockedPair))
  const [symbol, setSymbol] = useState(() => {
    if (lockedPair) return lockedPair
    try {
      const saved = sessionStorage.getItem('jm_lab_trade_symbol')
      if (saved && PAIRS.includes(saved)) return saved
    } catch {
      /* ignore */
    }
    return 'EURUSD'
  })
  const [booting, setBooting] = useState(false)
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

  useEffect(() => {
    if (lockedPair) setLabSessionPair(lockedPair)
  }, [lockedPair])

  useEffect(() => {
    if (!lockedPair || session || booting) return undefined
    let alive = true
    ;(async () => {
      setBooting(true)
      setError('')
      try {
        const s = await ensurePairAccount(lockedPair)
        if (!alive) return
        saveLabSession(s, lockedPair)
        setSession(s)
        setNote(`${lockedPair} demo ready · auto ON · account ${s.code}`)
      } catch (e) {
        if (alive) setError(e.message || String(e))
      } finally {
        if (alive) setBooting(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [lockedPair, session, booting])

  const refresh = useCallback(async () => {
    if (!session) return
    const [acc, pos, tr, tk, au] = await Promise.all([
      labTradeApi.account(session),
      labTradeApi.positions(session),
      labTradeApi.trades(session),
      labTradeApi.ticks(),
      labTradeApi.auto(session),
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
      let s
      if (lockedPair) {
        s = await ensurePairAccount(lockedPair)
      } else {
        const res = await labTradeApi.createAccount(10000, 'Lab live demo')
        s = {
          account_id: res.account.account_id,
          token: res.token,
          code: res.account.code,
        }
        setAccount(res.account)
        setNote(res.message || 'Demo account ready')
      }
      saveLabSession(s, lockedPair)
      setSession(s)
      if (lockedPair) setNote(`${lockedPair} demo account ${s.code} ready`)
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    saveLabSession(null, lockedPair)
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
      const p = PAIR_PRESETS[symbol] || PAIR_PRESETS.EURUSD
      const res = await labTradeApi.setAuto(
        {
          enabled: on,
          symbol,
          strategy: p.strategy,
          lots: Number(lots),
          sl_pips: Number(slPips),
          tp_pips: Number(tpPips),
        },
        session,
      )
      setAuto(res.auto)
      const name = res.strategy_info?.name || STRATEGY_INFO[p.strategy]?.name || p.strategy
      setNote(on ? `Auto ON · ${symbol} · ${name}` : 'Auto trading OFF')
      await refresh()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  const tick = ticks[symbol]
  const open = positions.filter((p) => p.status === 'OPEN')
  const pairGuide = useMemo(() => PAIR_GUIDE.find((p) => p.id === symbol), [symbol])
  const pairPreset = PAIR_PRESETS[symbol] || PAIR_PRESETS.EURUSD
  const stratInfo = STRATEGY_INFO[auto?.strategy || pairPreset.strategy] || {}

  function applyPairPreset(id) {
    const p = PAIR_PRESETS[id] || PAIR_PRESETS.EURUSD
    setLots(String(p.lots))
    setSlPips(String(p.sl_pips))
    setTpPips(String(p.tp_pips))
  }

  useEffect(() => {
    applyPairPreset(symbol)
  }, [symbol])

  if (!session) {
    return (
      <div className="lab-page">
        <header className="lab-page-head">
          <h1>{lockedPair ? `${lockedPair} live demo` : 'Live demo trading'}</h1>
          <p className="lab-muted">
            Paper money · live market prices · separate from JM FX gold desk.
          </p>
        </header>
        <section className="lab-panel lab-trade-start">
          {booting ? (
            <>
              <h2>Setting up {lockedPair}…</h2>
              <p className="lab-muted">Creating demo account and starting auto-trader…</p>
            </>
          ) : (
            <>
              <h2>{lockedPair ? `Start ${lockedPair} demo` : 'Start lab demo account'}</h2>
              <p>
                $10,000 virtual balance · chart + auto strategy
                {lockedPair ? ` · dedicated ${lockedPair} account` : ''}
              </p>
              <button type="button" className="lab-btn" disabled={busy} onClick={createDemo}>
                {lockedPair ? `Connect ${lockedPair} account` : 'Create demo account'}
              </button>
            </>
          )}
          {error ? <p className="lab-error-inline">{error}</p> : null}
        </section>
      </div>
    )
  }

  return (
    <div className="lab-page">
      <header className="lab-page-head lab-trade-head">
        <div>
          <h1>{lockedPair ? `${lockedPair} live demo` : 'Live demo trading'}</h1>
          <p className="lab-muted">
            Account <strong>{session.code}</strong> · paper only · max 1 open position
            {lockedPair ? ` · ${lockedPair} only` : ''}
          </p>
        </div>
        {!lockedPair ? (
          <button type="button" className="lab-btn lab-btn-ghost" onClick={logout}>
            New account
          </button>
        ) : (
          <button type="button" className="lab-btn lab-btn-ghost" onClick={logout}>
            Reset session
          </button>
        )}
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
        {lockedPair ? (
          <div className="lab-pair-bar lab-pair-bar-links">
            <span className="lab-muted">Open other pairs in new tab:</span>
            {PAIR_URL_SYMBOLS.filter((id) => id !== lockedPair).map((id) => (
              <a key={id} href={pairTradePath(id)} target="_blank" rel="noopener noreferrer">
                {id}
              </a>
            ))}
          </div>
        ) : (
          <div className="lab-pair-bar">
            {PAIRS.map((id) => (
              <button
                key={id}
                type="button"
                className={symbol === id ? 'on' : ''}
                onClick={() => {
                  setSymbol(id)
                  applyPairPreset(id)
                  try {
                    sessionStorage.setItem('jm_lab_trade_symbol', id)
                  } catch {
                    /* ignore */
                  }
                }}
              >
                {id}
              </button>
            ))}
          </div>
        )}
        <LabCandleChart symbol={symbol} livePrice={tick?.mid} positions={open} />
        {pairGuide ? (
          <p className="lab-muted lab-pair-hint">
            <strong>{pairGuide.botStyle}</strong> · {pairGuide.note}
          </p>
        ) : null}
      </section>

      <section className="lab-panel">
        <div className="lab-auto-head">
          <h2>Auto · {auto?.strategy_name || stratInfo.name || pairPreset.label}</h2>
          <span className={`lab-auto-pill ${auto?.enabled ? 'on' : ''}`}>
            {auto?.enabled ? 'Running' : 'Off'}
          </span>
        </div>
        <p className="lab-muted lab-auto-desc">
          {auto?.strategy_description || stratInfo.description || pairPreset.label}
          {' · '}
          Auto-fills on new M5 bar when flat · max 1 position.
        </p>
        <p className="lab-muted lab-auto-pair-tag">
          Pair preset: <strong>{symbol}</strong> → {pairPreset.label}
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
