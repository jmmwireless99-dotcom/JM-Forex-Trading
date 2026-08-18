import { useEffect, useState } from 'react'
import { investApi } from './investApi'
import './Investment.css'

function money(n) {
  return Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export default function AdminPanel() {
  const [stats, setStats] = useState(null)
  const [accounts, setAccounts] = useState([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setBusy(true)
        const [s, a] = await Promise.all([
          investApi.adminStats(),
          investApi.adminAccounts(),
        ])
        if (!alive) return
        setStats(s)
        setAccounts(a.accounts || [])
      } catch (e) {
        if (alive) setError(e.message || 'Failed to load admin panel')
      } finally {
        if (alive) setBusy(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  if (busy) {
    return (
      <div className="invest-app">
        <p className="invest-loading">Loading admin panel…</p>
      </div>
    )
  }

  return (
    <div className="invest-app">
      <header className="invest-hero">
        <div>
          <p className="invest-kicker">JM FX · Admin</p>
          <h1 className="invest-title">Investment Admin Panel</h1>
          <p className="invest-sub">Lahat ng investor accounts sa isang view</p>
        </div>
      </header>

      {error && <div className="invest-error">{error}</div>}

      {stats && (
        <section className="invest-grid">
          <article className="invest-card invest-card-main">
            <p className="invest-label">Total AUM (Balance)</p>
            <p className="invest-balance">${money(stats.total_balance)}</p>
          </article>
          <article className="invest-card">
            <p className="invest-label">Investors</p>
            <p className="invest-value">{stats.investors}</p>
          </article>
          <article className="invest-card">
            <p className="invest-label">Accounts</p>
            <p className="invest-value">{stats.accounts}</p>
          </article>
          <article className="invest-card">
            <p className="invest-label">Total Deposited</p>
            <p className="invest-value">${money(stats.total_deposited)}</p>
          </article>
          <article className="invest-card">
            <p className="invest-label">Total Withdrawn</p>
            <p className="invest-value">${money(stats.total_withdrawn)}</p>
          </article>
          <article className="invest-card invest-card-earn">
            <p className="invest-label">Total Earnings Paid</p>
            <p className="invest-value invest-positive">+${money(stats.total_earned)}</p>
          </article>
        </section>
      )}

      <section className="invest-panel">
        <h2>All investor accounts</h2>
        {!accounts.length ? (
          <p className="invest-empty">No accounts yet.</p>
        ) : (
          <div className="invest-table-wrap">
            <table className="invest-table">
              <thead>
                <tr>
                  <th>Investor</th>
                  <th>Email</th>
                  <th>Code</th>
                  <th>Deposited</th>
                  <th>Withdrawn</th>
                  <th>Earned</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((row) => (
                  <tr key={row.account_id}>
                    <td>{row.user?.full_name || row.account_label}</td>
                    <td>{row.user?.email || '—'}</td>
                    <td>{row.account_code}</td>
                    <td>${money(row.total_deposited)}</td>
                    <td>${money(row.total_withdrawn)}</td>
                    <td className="invest-positive">+${money(row.total_earned)}</td>
                    <td><strong>${money(row.balance)}</strong></td>
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
