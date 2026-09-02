import { useCallback, useEffect, useMemo, useState } from 'react'
import LabCandleChart from '../LabCandleChart.jsx'
import { PAIR_GUIDE, PAIR_PRESETS, STRATEGY_INFO } from '../content/compare.js'
import { labTradeApi, loadLabSession, saveLabSession, ensurePairAccount, setLabSessionPair, isInvalidLabSessionError } from '../api.js'
import { PAIR_URL_SYMBOLS, pairTradePath } from '../routing.js'
import { pipsFromEntryPrice, pipSize, positionStopPips, pricesFromEntryPips } from '../pips.js'

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

function fmtLevel(symbol, n) {
  if (n == null || n === '') return '—'
  const v = Number(n)
  return Number.isFinite(v) ? fmtPrice(symbol, v) : '—'
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
  const [lots, setLots] = useState('0.03')
  const [slPips, setSlPips] = useState('15')
  const [tpPips, setTpPips] = useState('30')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [editSl, setEditSl] = useState('')
  const [editTp, setEditTp] = useState('')
  const [editSlPips, setEditSlPips] = useState('')
  const [editTpPips, setEditTpPips] = useState('')

  useEffect(() => {
    if (lockedPair) setLabSessionPair(lockedPair)
  }, [lockedPair])

  useEffect(() => {
    if (!lockedPair) return undefined

    let cancelled = false
    setBooting(true)
    setError('')
    ;(async () => {
      try {
        const s = await ensurePairAccount(lockedPair)
        if (cancelled) return
        saveLabSession(s, lockedPair)
        setSession(s)
        setNote(`${lockedPair} demo ready · account ${s.code}`)
      } catch (e) {
        if (!cancelled) setError(e.message || String(e))
      } finally {
        if (!cancelled) setBooting(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [lockedPair])

  const refresh = useCallback(async () => {
    if (!session) return
    try {
      const [acc, pos, tr, au] = await Promise.all([
        labTradeApi.account(session),
        labTradeApi.positions(session),
        labTradeApi.trades(session),
        labTradeApi.auto(session),
      ])
      setAccount(acc)
      setAuto(au)
      setPositions(pos.positions || [])
      setTrades(tr.trades || [])
    } catch (e) {
      if (lockedPair && isInvalidLabSessionError(e)) {
        const s = await ensurePairAccount(lockedPair)
        saveLabSession(s, lockedPair)
        setSession(s)
        setNote(`${lockedPair} session refreshed · account ${s.code}`)
        return
      }
      throw e
    }
  }, [session, lockedPair])

  const refreshTick = useCallback(async () => {
    try {
      const row = await labTradeApi.quote(symbol, true)
      if (row?.mid != null) {
        setTicks((prev) => ({ ...prev, [symbol]: row }))
      }
    } catch {
      /* keep last tick */
    }
  }, [symbol])

  useEffect(() => {
    if (!session) return undefined
    let alive = true
    ;(async () => {
      try {
        const synced = await labTradeApi.syncAutoPreset(session)
        if (!alive) return
        if (synced?.auto) {
          setAuto(synced.auto)
          setLots(String(synced.auto.lots))
          setSlPips(String(synced.auto.sl_pips))
          setTpPips(String(synced.auto.tp_pips))
          if (synced.message) setNote(synced.message)
        }
        await Promise.all([refresh(), refreshTick()])
        if (alive) setError('')
      } catch (e) {
        if (alive) setError(e.message || String(e))
      }
    })()
    const tickId = setInterval(() => {
      refreshTick().catch(() => {})
    }, 400)
    const accId = setInterval(() => {
      refresh().catch(() => {})
    }, 1500)
    return () => {
      alive = false
      clearInterval(tickId)
      clearInterval(accId)
    }
  }, [session, refresh, refreshTick])

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

  async function syncAutoStopPips(p) {
    if (!session || !p) return
    const { sl, tp } = positionStopPips(p)
    if (sl == null || tp == null) return
    const res = await labTradeApi.setAuto({ sl_pips: sl, tp_pips: tp }, session)
    setAuto(res.auto)
    setSlPips(String(sl))
    setTpPips(String(tp))
    setNote(`SL / TP · ${sl} pips SL · ${tp} pips TP (from entry)`)
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

  const handleUpdateStops = useCallback(
    async (positionId, body) => {
      if (!session) return
      await labTradeApi.updatePositionStops(positionId, body, session)
      const posRes = await labTradeApi.positions(session)
      const list = posRes.positions || []
      setPositions(list)
      const p = list.find((x) => x.id === positionId)
      if (p) await syncAutoStopPips(p)
      else await refresh()
    },
    [session, refresh],
  )

  async function saveStops(positionId, p) {
    setBusy(true)
    setError('')
    try {
      const sl = editSl.trim() === '' ? null : Number(editSl)
      const tp = editTp.trim() === '' ? null : Number(editTp)
      const slP = editSlPips.trim() === '' ? null : Number(editSlPips)
      const tpP = editTpPips.trim() === '' ? null : Number(editTpPips)
      const body = {}
      if (sl != null && Number.isFinite(sl)) body.stop_loss = sl
      if (tp != null && Number.isFinite(tp)) body.take_profit = tp
      if (!Object.keys(body).length && slP != null && tpP != null && p) {
        const lv = pricesFromEntryPips(p.symbol, p.side, p.entry_price, slP, tpP)
        if (lv) {
          body.stop_loss = lv.stop_loss
          body.take_profit = lv.take_profit
        }
      }
      if (!Object.keys(body).length) throw new Error('Enter SL/TP price or pips')
      await labTradeApi.updatePositionStops(positionId, body, session)
      setNote('SL / TP updated')
      await refresh()
      if (p) await syncAutoStopPips({ ...p, stop_loss: body.stop_loss ?? p.stop_loss, take_profit: body.take_profit ?? p.take_profit })
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

  const openPos = positions.filter((p) => p.status === 'OPEN')
  const open = openPos.filter((p) => p.symbol === symbol)
  const openForChart = openPos

  useEffect(() => {
    const p = open[0]
    if (!p) {
      setEditSl('')
      setEditTp('')
      return
    }
    setEditSl(p.stop_loss != null ? fmtPrice(p.symbol, p.stop_loss) : '')
    setEditTp(p.take_profit != null ? fmtPrice(p.symbol, p.take_profit) : '')
    const slP =
      p.stop_loss != null ? pipsFromEntryPrice(p.symbol, p.side, p.entry_price, p.stop_loss, 'sl') : null
    const tpP =
      p.take_profit != null ? pipsFromEntryPrice(p.symbol, p.side, p.entry_price, p.take_profit, 'tp') : null
    setEditSlPips(slP != null ? String(slP) : '')
    setEditTpPips(tpP != null ? String(tpP) : '')
  }, [open.length, open[0]?.id, open[0]?.stop_loss, open[0]?.take_profit])

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
          <strong className="lab-live-price">{tick ? fmtPrice(symbol, tick.mid) : '—'}</strong>
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
        <LabCandleChart
          symbol={symbol}
          livePrice={tick?.mid}
          positions={openForChart}
          onUpdateStops={open.length ? handleUpdateStops : null}
        />
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
            <div key={p.id} className="lab-open-pos">
              <div className="lab-trade-row">
                <span>
                  {p.side} {p.symbol} · {p.lots} lot(s)
                </span>
                <span className={p.unrealized_pnl >= 0 ? 'lab-pos' : 'lab-neg'}>
                  uP&amp;L ${money(p.unrealized_pnl)}
                </span>
                <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => closeOpen(p.id)}>
                  Close
                </button>
              </div>
              <div className="lab-levels-row">
                <span>
                  <em>Entry</em> {fmtLevel(p.symbol, p.entry_price)}
                </span>
                <span>
                  <em>SL</em> {fmtLevel(p.symbol, p.stop_loss)}
                  {(() => {
                    const sp = positionStopPips(p).sl
                    return sp != null ? <strong className="lab-pip-tag"> · {sp} pips</strong> : null
                  })()}
                </span>
                <span>
                  <em>TP</em> {fmtLevel(p.symbol, p.take_profit)}
                  {(() => {
                    const tpP = positionStopPips(p).tp
                    return tpP != null ? <strong className="lab-pip-tag"> · {tpP} pips</strong> : null
                  })()}
                </span>
              </div>
              <div className="lab-stops-edit">
                <p className="lab-muted lab-stops-hint">
                  Adjust SL / TP on chart (drag lines) or edit pips / prices below · entry{' '}
                  {fmtPrice(p.symbol, p.entry_price)}
                </p>
                <div className="lab-trade-controls">
                  <label>
                    SL (pips)
                    <input
                      type="number"
                      step="1"
                      min="1"
                      value={editSlPips}
                      onChange={(e) => {
                        setEditSlPips(e.target.value)
                        const lv = pricesFromEntryPips(p.symbol, p.side, p.entry_price, e.target.value, editTpPips)
                        if (lv) {
                          setEditSl(fmtPrice(p.symbol, lv.stop_loss))
                          setEditTp(fmtPrice(p.symbol, lv.take_profit))
                        }
                      }}
                    />
                  </label>
                  <label>
                    TP (pips)
                    <input
                      type="number"
                      step="1"
                      min="1"
                      value={editTpPips}
                      onChange={(e) => {
                        setEditTpPips(e.target.value)
                        const lv = pricesFromEntryPips(p.symbol, p.side, p.entry_price, editSlPips, e.target.value)
                        if (lv) {
                          setEditSl(fmtPrice(p.symbol, lv.stop_loss))
                          setEditTp(fmtPrice(p.symbol, lv.take_profit))
                        }
                      }}
                    />
                  </label>
                  <label>
                    Stop loss
                    <input
                      type="number"
                      step={symbol === 'XAUUSD' ? '0.01' : '0.00001'}
                      value={editSl}
                      onChange={(e) => {
                        setEditSl(e.target.value)
                        const n = Number(e.target.value)
                        if (Number.isFinite(n)) {
                          const sp = pipsFromEntryPrice(p.symbol, p.side, p.entry_price, n, 'sl')
                          if (sp != null) setEditSlPips(String(sp))
                        }
                      }}
                    />
                  </label>
                  <label>
                    Take profit
                    <input
                      type="number"
                      step={symbol === 'XAUUSD' ? '0.01' : '0.00001'}
                      value={editTp}
                      onChange={(e) => {
                        setEditTp(e.target.value)
                        const n = Number(e.target.value)
                        if (Number.isFinite(n)) {
                          const tpP = pipsFromEntryPrice(p.symbol, p.side, p.entry_price, n, 'tp')
                          if (tpP != null) setEditTpPips(String(tpP))
                        }
                      }}
                    />
                  </label>
                  <button type="button" className="lab-btn" disabled={busy} onClick={() => saveStops(p.id, p)}>
                    Update SL / TP
                  </button>
                </div>
              </div>
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
                  <th>Entry</th>
                  <th>SL</th>
                  <th>TP</th>
                  <th>Exit</th>
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
                    <td>{fmtLevel(t.symbol, t.entry_price)}</td>
                    <td>{fmtLevel(t.symbol, t.stop_loss)}</td>
                    <td>{fmtLevel(t.symbol, t.take_profit)}</td>
                    <td>{fmtLevel(t.symbol, t.exit_price)}</td>
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
