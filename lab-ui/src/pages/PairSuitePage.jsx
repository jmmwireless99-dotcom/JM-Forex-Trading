import { useCallback, useEffect, useState } from 'react'
import { PAIR_PRESETS, STRATEGY_INFO } from '../content/compare.js'
import {
  labTradeApi,
  loadPairSuite,
  saveLabSession,
  savePairSuite,
} from '../api.js'

const SUITE_PAIRS = ['EURUSD', 'GBPUSD', 'AUDNZD', 'EURCHF', 'XAUUSD']

function fmtPrice(symbol, n) {
  const d = symbol === 'XAUUSD' ? 2 : 5
  return Number(n || 0).toFixed(d)
}

function fmtLevel(symbol, n) {
  if (n == null || n === '') return '—'
  const v = Number(n)
  return Number.isFinite(v) ? fmtPrice(symbol, v) : '—'
}

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function sessionFromRow(row) {
  return {
    account_id: row.account_id,
    token: row.token,
    code: row.code,
    symbol: row.symbol,
  }
}

export default function PairSuitePage() {
  const [suite, setSuite] = useState(() => loadPairSuite())
  const [rows, setRows] = useState([])
  const [ticks, setTicks] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const refresh = useCallback(async () => {
    if (!suite?.accounts?.length) return
    const tk = await labTradeApi.ticks()
    setTicks(tk.ticks || {})
    const snapshots = await Promise.all(
      suite.accounts.map(async (acc) => {
        const session = sessionFromRow(acc)
        const [account, auto, positions] = await Promise.all([
          labTradeApi.account(session),
          labTradeApi.auto(session),
          labTradeApi.positions(session),
        ])
        return {
          ...acc,
          account,
          auto,
          positions: (positions.positions || []).filter((p) => p.status === 'OPEN'),
        }
      }),
    )
    setRows(snapshots)
  }, [suite])

  useEffect(() => {
    if (!suite?.accounts?.length) return undefined
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
  }, [suite, refresh])

  useEffect(() => {
    if (!suite?.accounts?.length) return undefined
    const have = new Set(suite.accounts.map((a) => a.symbol))
    const missing = SUITE_PAIRS.filter((sym) => !have.has(sym))
    if (!missing.length) return undefined

    let cancelled = false
    ;(async () => {
      try {
        const res = await labTradeApi.createPairSuite(10000, false)
        const accounts = (res.accounts || []).map((a) => ({
          symbol: a.symbol,
          account_id: a.account_id,
          code: a.code,
          token: a.token,
          label: a.label,
          strategy: a.strategy,
        }))
        if (cancelled || accounts.length < SUITE_PAIRS.length) return
        const payload = { accounts, created_at: suite.created_at || new Date().toISOString() }
        savePairSuite(payload)
        setSuite(payload)
        setNote(`Added missing pair(s): ${missing.join(', ')}`)
      } catch (e) {
        if (!cancelled) setError(e.message || String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [suite])

  async function bootstrap(startAuto = true) {
    setBusy(true)
    setError('')
    try {
      const res = await labTradeApi.createPairSuite(10000, startAuto)
      const accounts = (res.accounts || []).map((a) => ({
        symbol: a.symbol,
        account_id: a.account_id,
        code: a.code,
        token: a.token,
        label: a.label,
        strategy: a.strategy,
      }))
      const payload = { accounts, created_at: new Date().toISOString() }
      savePairSuite(payload)
      setSuite(payload)
      setNote(res.message || 'Pair suite created — auto running on server')
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  async function toggleAll(on) {
    if (!suite?.accounts?.length) return
    setBusy(true)
    setError('')
    try {
      await Promise.all(
        suite.accounts.map((acc) => {
          const p = PAIR_PRESETS[acc.symbol] || PAIR_PRESETS.EURUSD
          return labTradeApi.setAuto(
            {
              enabled: on,
              symbol: acc.symbol,
              strategy: p.strategy,
              lots: p.lots,
              sl_pips: p.sl_pips,
              tp_pips: p.tp_pips,
            },
            sessionFromRow(acc),
          )
        }),
      )
      setNote(on ? 'All 5 pair autos started' : 'All 5 pair autos stopped')
      await refresh()
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  function openInTrade(acc) {
    window.open(`/lab/${acc.symbol}`, '_blank', 'noopener,noreferrer')
  }

  function resetSuite() {
    savePairSuite(null)
    setSuite(null)
    setRows([])
    setNote('Cleared local pair suite — create again to get fresh credentials')
  }

  if (!suite?.accounts?.length) {
    return (
      <div className="lab-page">
        <header className="lab-page-head">
          <h1>5-pair dry run</h1>
          <p className="lab-muted">
            Isang account bawat pair — tumatakbo sabay sa server kahit iisa lang ang browser mo.
          </p>
        </header>
        <section className="lab-panel">
          <h2>Pair test suite</h2>
          <p className="lab-muted">
            Gagawa ng 5 demo accounts: <strong>EURUSD</strong>, <strong>GBPUSD</strong>,{' '}
            <strong>AUDNZD</strong>, <strong>EURCHF</strong>, <strong>XAUUSD</strong>. Bawat isa may
            sariling strategy preset at auto-trader. Puwedeng i-monitor lahat dito nang sabay.
          </p>
          <ul className="lab-suite-list">
            {SUITE_PAIRS.map((id) => {
              const p = PAIR_PRESETS[id]
              return (
                <li key={id}>
                  <strong>{id}</strong> · {p.label} · {STRATEGY_INFO[p.strategy]?.name || p.strategy}
                </li>
              )
            })}
          </ul>
          <div className="lab-trade-controls">
            <button type="button" className="lab-btn" disabled={busy} onClick={() => bootstrap(true)}>
              Create 5 accounts + start auto
            </button>
            <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => bootstrap(false)}>
              Create 5 accounts only
            </button>
          </div>
          {error ? <p className="lab-error-inline">{error}</p> : null}
          {note ? <p className="lab-note">{note}</p> : null}
        </section>
      </div>
    )
  }

  return (
    <div className="lab-page">
      <header className="lab-page-head lab-trade-head">
        <div>
          <h1>5-pair dry run</h1>
          <p className="lab-muted">
            5 accounts · tumatakbo sabay sa server · refresh every 4s
          </p>
        </div>
        <div className="lab-suite-actions">
          <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => toggleAll(true)}>
            Start all
          </button>
          <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={() => toggleAll(false)}>
            Stop all
          </button>
          <button type="button" className="lab-btn lab-btn-ghost" disabled={busy} onClick={resetSuite}>
            Reset local
          </button>
        </div>
      </header>

      {error ? <div className="lab-error-box">{error}</div> : null}
      {note ? <p className="lab-note">{note}</p> : null}

      <p className="lab-muted lab-suite-tip">
        Tip: Puwedeng buksan ang <strong>Live demo</strong> tab sa ibang browser window (o incognito) at
        piliin ang ibang account gamit ang &quot;Open trade view&quot; — lahat ng auto tumatakbo pa rin sa
        background.
      </p>

      <div className="lab-suite-grid">
        {rows.map((row) => {
          const preset = PAIR_PRESETS[row.symbol] || PAIR_PRESETS.EURUSD
          const strat = STRATEGY_INFO[row.auto?.strategy || preset.strategy] || {}
          const tick = ticks[row.symbol]
          const open = row.positions?.[0]
          return (
            <article key={row.account_id} className="lab-panel lab-suite-card">
              <div className="lab-suite-card-head">
                <h2>{row.symbol}</h2>
                <span className={`lab-auto-pill ${row.auto?.enabled ? 'on' : ''}`}>
                  {row.auto?.enabled ? 'Auto ON' : 'Auto OFF'}
                </span>
              </div>
              <p className="lab-muted">
                Account <strong>{row.code}</strong> · {preset.label}
              </p>
              <p className="lab-muted lab-auto-desc">{strat.description || preset.label}</p>
              <div className="lab-suite-stats">
                <div>
                  <span className="lab-stat-label">Balance</span>
                  <strong>${money(row.account?.balance)}</strong>
                </div>
                <div>
                  <span className="lab-stat-label">Equity</span>
                  <strong>${money(row.account?.equity)}</strong>
                </div>
                <div>
                  <span className="lab-stat-label">Daily P&amp;L</span>
                  <strong className={row.account?.daily_pnl >= 0 ? 'lab-pos' : 'lab-neg'}>
                    ${money(row.account?.daily_pnl)}
                  </strong>
                </div>
                <div>
                  <span className="lab-stat-label">Live</span>
                  <strong>{tick ? Number(tick.mid).toFixed(row.symbol === 'XAUUSD' ? 2 : 5) : '—'}</strong>
                </div>
              </div>
              {row.auto?.last_block_reason ? (
                <p className="lab-block-reason">{row.auto.last_block_reason}</p>
              ) : (
                <p className="lab-muted">Waiting for next M5 bar close…</p>
              )}
              {open ? (
                <>
                  <p className="lab-suite-open">
                    Open: {open.side} {open.lots} lot(s) · uP&amp;L{' '}
                    <span className={open.unrealized_pnl >= 0 ? 'lab-pos' : 'lab-neg'}>
                      ${money(open.unrealized_pnl)}
                    </span>
                  </p>
                  <p className="lab-suite-levels lab-muted">
                    Entry {fmtLevel(row.symbol, open.entry_price)} · SL {fmtLevel(row.symbol, open.stop_loss)} · TP{' '}
                    {fmtLevel(row.symbol, open.take_profit)}
                  </p>
                </>
              ) : (
                <p className="lab-muted">Flat</p>
              )}
              {(row.auto?.recent_signals || []).length > 0 ? (
                <p className="lab-muted lab-suite-signal">
                  Last signal: {row.auto.recent_signals[0].side} · {row.auto.recent_signals[0].reason}
                </p>
              ) : null}
              <button type="button" className="lab-btn lab-btn-ghost" onClick={() => openInTrade(row)}>
                Open trade view
              </button>
            </article>
          )
        })}
      </div>
    </div>
  )
}
