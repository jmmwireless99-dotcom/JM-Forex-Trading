import { useEffect, useRef, useState } from 'react'
import { investApi, loadAuthSession } from './investApi'
import './Investment.css'

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function referralLinkFromAccount(account) {
  if (account?.referral_link) return account.referral_link
  const code = account?.referral_code || account?.account_code
  if (!code) return ''
  const base = `${window.location.origin}${import.meta.env.BASE_URL || '/fx/'}`.replace(/\/+$/, '')
  return `${base}/?mode=register&ref=${encodeURIComponent(code)}`
}

export default function InvestmentDashboard({ focusReferral = false }) {
  const [account, setAccount] = useState(null)
  const [user, setUser] = useState(() => loadAuthSession()?.user)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cashInAmt, setCashInAmt] = useState('1000')
  const [cashOutAmt, setCashOutAmt] = useState('')
  const [modal, setModal] = useState(null)
  const [copied, setCopied] = useState(false)
  const referralRef = useRef(null)

  async function copyReferralLink() {
    const link = referralLinkFromAccount(account)
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setBusy(true)
        const res = await investApi.account()
        if (alive) {
          setAccount(res.account)
          setUser(res.user)
        }
      } catch (e) {
        if (alive) setError(e.message || 'Failed to load investment account')
      } finally {
        if (alive) setBusy(false)
      }
    })()
    const timer = setInterval(() => {
      investApi.account().then((r) => {
        setAccount(r.account)
        setUser(r.user)
      }).catch(() => {})
    }, 60000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (focusReferral && account && referralRef.current) {
      referralRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [focusReferral, account])

  async function handleCashIn() {
    setError('')
    setBusy(true)
    try {
      const res = await investApi.cashIn(cashInAmt, 'Cash in')
      setAccount(res.account)
      setModal(null)
    } catch (e) {
      setError(e.message || 'Cash in failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleCashOut() {
    setError('')
    setBusy(true)
    try {
      const res = await investApi.cashOut(cashOutAmt, 'Withdrawal')
      setAccount(res.account)
      setModal(null)
      setCashOutAmt('')
    } catch (e) {
      setError(e.message || 'Withdrawal failed')
    } finally {
      setBusy(false)
    }
  }

  if (!account && busy) {
    return (
      <div className="invest-app">
        <p className="invest-loading">Loading investment dashboard…</p>
      </div>
    )
  }

  if (!account) {
    return (
      <div className="invest-app">
        <div className="invest-error">Failed to load account. Try logout and login again.</div>
      </div>
    )
  }

  const referralLink = referralLinkFromAccount(account)
  const referralCode = account.referral_code || account.account_code

  const dailyPct = account?.daily_rate_pct ?? 0
  const periodPct = account?.period_rate_pct ?? account?.monthly_rate_pct ?? 30
  const periodDays = account?.period_days ?? account?.working_days_per_month ?? 30

  return (
    <div className="invest-app">
      <header className="invest-hero">
        <div>
          <p className="invest-kicker">JM FX · Investment Account</p>
          <h1 className="invest-title">My Investment Dashboard</h1>
          <p className="invest-sub">
            Welcome, {user?.full_name || user?.email || 'Investor'} · {periodPct}% in {periodDays} days
          </p>
        </div>
        <div className="invest-badge">
          <span>{account?.account_code || '—'}</span>
          <small>{account?.account_label || 'Investor'}</small>
        </div>
      </header>

      {error && <div className="invest-error">{error}</div>}

      <section ref={referralRef} className="invest-rate-box invest-referral-box invest-referral-top">
        <h2>Your referral link — earn 5%</h2>
        <p className="invest-note">
          I-share ang link na ito. Kapag mag-register at kumita ang under mo,{' '}
          <strong>{account.referral_rate_pct ?? 5}%</strong> ng daily investment earnings nila ay sa iyo.
        </p>
        <div className="invest-referral-row">
          <code className="invest-referral-link">{referralLink || '—'}</code>
          <button type="button" className="invest-btn invest-btn-in" onClick={copyReferralLink} disabled={!referralLink}>
            {copied ? 'Copied!' : 'Copy link'}
          </button>
        </div>
        <p className="invest-meta">
          Referral code: <strong>{referralCode || '—'}</strong>
        </p>
      </section>

      <section className="invest-actions">
        <button
          type="button"
          className="invest-btn invest-btn-in"
          onClick={() => setModal('in')}
          disabled={busy}
        >
          + Cash In
        </button>
        <button
          type="button"
          className="invest-btn invest-btn-out"
          onClick={() => {
            setCashOutAmt(String(account?.balance || ''))
            setModal('out')
          }}
          disabled={busy || !account?.balance}
        >
          Cash Out / Withdraw
        </button>
      </section>

      <section className="invest-grid">
        <article className="invest-card invest-card-main">
          <p className="invest-label">Total Balance</p>
          <p className="invest-balance">${money(account?.balance)}</p>
          <p className="invest-meta">{account?.currency || 'USD'}</p>
        </article>

        <article className="invest-card">
          <p className="invest-label">Total Deposited</p>
          <p className="invest-value">${money(account?.total_deposited)}</p>
        </article>

        <article className="invest-card">
          <p className="invest-label">Total Withdrawn</p>
          <p className="invest-value">${money(account?.total_withdrawn)}</p>
        </article>

        <article className="invest-card">
          <p className="invest-label">Net Principal</p>
          <p className="invest-value">${money(account?.net_principal)}</p>
        </article>

        <article className="invest-card invest-card-earn">
          <p className="invest-label">Total Earnings</p>
          <p className="invest-value invest-positive">+${money(account?.total_earned)}</p>
        </article>

        <article className="invest-card invest-card-earn">
          <p className="invest-label">Referral Earnings (5%)</p>
          <p className="invest-value invest-positive">+${money(account?.referral_earned)}</p>
          <p className="invest-meta">{account?.referral_count ?? 0} referred</p>
        </article>

        <article className="invest-card">
          <p className="invest-label">Today&apos;s Earning (est.)</p>
          <p className="invest-value invest-positive">
            +${money(account?.projected_today)}
          </p>
          <p className="invest-meta">{dailyPct}% / day</p>
        </article>
      </section>

      <section className="invest-rate-box">
        <h2>Return breakdown</h2>
        <div className="invest-rate-row">
          <span>Period return</span>
          <strong>{periodPct}% in {periodDays} days</strong>
        </div>
        <div className="invest-rate-row">
          <span>Daily rate</span>
          <strong>{dailyPct}%</strong>
        </div>
        <p className="invest-note">
          Formula: {periodPct}% ÷ {periodDays} days = {dailyPct}% daily earning on your balance.
          Earnings accrue automatically each day when you open the dashboard.
        </p>
      </section>

      {account.referrals?.length > 0 && (
        <section className="invest-panel">
          <h2>Your referrals (under you)</h2>
          <div className="invest-table-wrap">
            <table className="invest-table">
              <thead>
                <tr>
                  <th>Investor</th>
                  <th>Code</th>
                  <th>Balance</th>
                  <th>Their earnings</th>
                </tr>
              </thead>
              <tbody>
                {account.referrals.map((r) => (
                  <tr key={r.account_code}>
                    <td>{r.label}</td>
                    <td>{r.account_code}</td>
                    <td>${money(r.balance)}</td>
                    <td className="invest-positive">+${money(r.total_earned)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="invest-panel">
        <h2>Buong buwan — daily earnings chart</h2>
        {!account?.earnings_month_chart?.length ? (
          <p className="invest-empty">Walang earnings chart pa — mag cash in para magsimula.</p>
        ) : (
          <div className="invest-earn-chart" role="img" aria-label="Daily earnings this month">
            {account.earnings_month_chart.map((row) => {
              const max = Math.max(
                ...account.earnings_month_chart.map((r) => Number(r.earning) || 0),
                0.01,
              )
              const pct = Math.max(4, (Number(row.earning) / max) * 100)
              return (
                <div key={row.date} className="invest-earn-bar-wrap" title={`${fmtDate(row.date)}: +$${money(row.earning)}`}>
                  <div
                    className={`invest-earn-bar${Number(row.earning) > 0 ? '' : ' zero'}`}
                    style={{ height: `${pct}%` }}
                  />
                  <span className="invest-earn-bar-label">{new Date(row.date).getDate()}</span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="invest-panel">
        <h2>Daily earnings</h2>
        {!account?.recent_earnings?.length ? (
          <p className="invest-empty">No earnings yet — cash in to start earning.</p>
        ) : (
          <div className="invest-table-wrap">
            <table className="invest-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Earning</th>
                  <th>Daily rate</th>
                  <th>Balance after</th>
                </tr>
              </thead>
              <tbody>
                {account.recent_earnings.map((row) => (
                  <tr key={row.date}>
                    <td>{fmtDate(row.date)}</td>
                    <td className="invest-positive">+${money(row.earning)}</td>
                    <td>{row.daily_rate_pct}%</td>
                    <td>${money(row.balance_after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="invest-meta">Naka-save ang earnings history — hindi nabubura sa deploy.</p>
          </div>
        )}
      </section>

      <section className="invest-panel">
        <h2>Transactions</h2>
        {!account?.recent_transactions?.length ? (
          <p className="invest-empty">No transactions yet.</p>
        ) : (
          <div className="invest-table-wrap">
            <table className="invest-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Note</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {account.recent_transactions.map((tx) => (
                  <tr key={tx.id}>
                    <td>
                      <span className={`invest-tag invest-tag-${tx.kind}`}>
                        {tx.kind === 'cash_in'
                          ? 'Cash In'
                          : tx.kind === 'referral'
                            ? 'Referral 5%'
                            : 'Withdrawal'}
                      </span>
                    </td>
                    <td className={
                      tx.kind === 'cash_in' || tx.kind === 'referral'
                        ? 'invest-positive'
                        : 'invest-negative'
                    }>
                      {tx.kind === 'cash_out' ? '-' : '+'}${money(tx.amount)}
                    </td>
                    <td>{tx.note || '—'}</td>
                    <td className="invest-meta">{fmtDate(tx.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {modal === 'in' && (
        <div className="invest-modal-backdrop" onClick={() => setModal(null)}>
          <div className="invest-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Cash In</h3>
            <p>Maglagay ng pera sa investment account mo.</p>
            <label>
              Amount (USD)
              <input
                type="number"
                min="1"
                step="0.01"
                value={cashInAmt}
                onChange={(e) => setCashInAmt(e.target.value)}
              />
            </label>
            <div className="invest-modal-actions">
              <button type="button" className="invest-btn-ghost" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button type="button" className="invest-btn invest-btn-in" onClick={handleCashIn} disabled={busy}>
                Confirm Cash In
              </button>
            </div>
          </div>
        </div>
      )}

      {modal === 'out' && (
        <div className="invest-modal-backdrop" onClick={() => setModal(null)}>
          <div className="invest-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Cash Out / Withdraw</h3>
            <p>Available balance: ${money(account?.balance)}</p>
            <label>
              Amount (USD)
              <input
                type="number"
                min="1"
                step="0.01"
                max={account?.balance}
                value={cashOutAmt}
                onChange={(e) => setCashOutAmt(e.target.value)}
              />
            </label>
            <div className="invest-modal-actions">
              <button type="button" className="invest-btn-ghost" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button type="button" className="invest-btn invest-btn-out" onClick={handleCashOut} disabled={busy}>
                Confirm Withdrawal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
