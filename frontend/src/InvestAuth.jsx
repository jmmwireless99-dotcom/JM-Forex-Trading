import { useState } from 'react'
import { investApi, saveAuthSession } from './investApi'
import './Investment.css'

function initialAuthMode(initialMode) {
  if (initialMode === 'register' || initialMode === 'login') return initialMode
  try {
    const params = new URLSearchParams(window.location.search)
    if (params.get('mode') === 'register') return 'register'
  } catch {
    /* ignore */
  }
  return 'login'
}

function initialReferralCode() {
  try {
    const params = new URLSearchParams(window.location.search)
    return (params.get('ref') || '').trim().toUpperCase()
  } catch {
    return ''
  }
}

export default function InvestAuth({ onSuccess, initialMode, showAdminHint = false }) {
  const [mode, setMode] = useState(() => initialAuthMode(initialMode))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [referralCode, setReferralCode] = useState(initialReferralCode)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res =
        mode === 'login'
          ? await investApi.login(email, password)
          : await investApi.register(email, password, fullName, referralCode)
      saveAuthSession(res)
      onSuccess?.(res)
    } catch (err) {
      setError(err.message || 'Authentication failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="invest-app invest-auth-wrap">
      <div className="invest-auth-card">
        <p className="invest-kicker">JM FX Investment</p>
        <h1 className="invest-title">{mode === 'login' ? 'Login' : 'Create Account'}</h1>
        <p className="invest-sub">
          {mode === 'login'
            ? 'Sign in to view your investment dashboard.'
            : 'Register to start earning 30% in 30 days.'}
        </p>

        {error && <div className="invest-error">{error}</div>}

        <form className="invest-auth-form" onSubmit={submit}>
          {mode === 'register' && (
            <label>
              Full name
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Juan Dela Cruz"
              />
            </label>
          )}
          {mode === 'register' && (
            <label>
              Referral code (optional)
              <input
                type="text"
                value={referralCode}
                onChange={(e) => setReferralCode(e.target.value.toUpperCase())}
                placeholder="ABC123"
              />
            </label>
          )}
          {mode === 'register' && referralCode && (
            <p className="invest-note">Referred by code: <code>{referralCode}</code></p>
          )}
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@email.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 6 characters"
            />
          </label>
          <button type="submit" className="invest-btn invest-btn-in" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Login' : 'Register'}
          </button>
        </form>

        <p className="invest-auth-switch">
          {mode === 'login' ? (
            <>
              Wala pang account?{' '}
              <button type="button" className="invest-link" onClick={() => setMode('register')}>
                Register here
              </button>
            </>
          ) : (
            <>
              May account na?{' '}
              <button type="button" className="invest-link" onClick={() => setMode('login')}>
                Login here
              </button>
            </>
          )}
        </p>

        <div className="invest-auth-links">
          <a className="invest-auth-pill" href="/fx/?mode=register">
            Investor Register
          </a>
          <a className="invest-auth-pill" href="/fx/?view=admin">
            Admin Panel Login
          </a>
        </div>

        <p className="invest-note invest-admin-hint">
          {showAdminHint
            ? 'Admin panel — login gamit ang admin email mo (hal. admin@jmfx.local).'
            : 'Admin login: use your admin email (default '}
          {!showAdminHint && (
            <>
              <code>admin@jmfx.local</code> / <code>admin123</code> — change in .env)
            </>
          )}
        </p>
      </div>
    </div>
  )
}
