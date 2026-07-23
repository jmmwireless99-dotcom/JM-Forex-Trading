import { useEffect, useState } from 'react'
import {
  loadRecentAccounts,
  loginAccount,
  registerAccount,
  api,
} from './api'

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve('')
      return
    }
    if (!file.type.startsWith('image/')) {
      reject(new Error('Logo must be an image (PNG/JPEG/WebP)'))
      return
    }
    if (file.size > 80_000) {
      reject(new Error('Logo too large — keep under ~80KB'))
      return
    }
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Could not read logo file'))
    reader.readAsDataURL(file)
  })
}

function AvatarMark({ avatar, label, code }) {
  if (avatar) {
    return <img className="acct-avatar" src={avatar} alt="" />
  }
  const letter = (label || code || '?').trim().charAt(0).toUpperCase() || '?'
  return <span className="acct-avatar acct-avatar-fallback">{letter}</span>
}

/**
 * Login / Register gate.
 * Username = MT5 account number · Password = MT5 password.
 * Server stores a hash only — trade journals never cleared on login.
 */
export default function AccountAuth({ onAuthed, initialTab = 'login' }) {
  const [tab, setTab] = useState(initialTab === 'register' ? 'register' : 'login')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [deposit, setDeposit] = useState('1000')
  const [avatar, setAvatar] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState('')
  const [recent, setRecent] = useState(() => loadRecentAccounts())

  useEffect(() => {
    setTab(initialTab === 'register' ? 'register' : 'login')
  }, [initialTab])

  useEffect(() => {
    setRecent(loadRecentAccounts())
  }, [tab])

  async function onLogoPick(e) {
    try {
      const data = await fileToDataUrl(e.target.files?.[0])
      setAvatar(data)
      setError('')
    } catch (err) {
      setError(err.message || 'Logo failed')
    }
  }

  async function previewCode(nextCode) {
    const cleaned = String(nextCode || '').trim()
    setCode(cleaned)
    if (cleaned.length < 5) {
      setHint('')
      return
    }
    try {
      const info = await api.lookupAccount(cleaned)
      setHint(`${info.label} · ${info.has_password ? 'password set' : 'no password yet'}`)
      if (info.avatar) setAvatar(info.avatar)
    } catch {
      setHint('')
    }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (tab === 'login') {
        const session = await loginAccount({ code, password })
        onAuthed(session)
      } else {
        const mt5 = String(code || '').trim()
        if (!/^\d{5,16}$/.test(mt5)) {
          throw new Error('MT5 account must be 5–16 digits')
        }
        if (!password || password.length < 6) {
          throw new Error('MT5 password must be at least 6 characters')
        }
        if (!firstName.trim() || !lastName.trim()) {
          throw new Error('First name and last name are required')
        }
        if (!email.trim() || !email.includes('@')) {
          throw new Error('Gmail / email is required')
        }
        const session = await registerAccount({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          mt5_login: mt5,
          password,
          deposit: Number(deposit) || 1000,
          avatar: avatar || undefined,
        })
        onAuthed(session)
      }
    } catch (err) {
      setError(err.message || 'Auth failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <h1 className="brand">
            JM <span>Forex</span>
          </h1>
          <p>
            Client login — <strong>username = MT5 account</strong>,{' '}
            <strong>password = MT5 password</strong>. History stays per account.
          </p>
        </div>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            className={tab === 'login' ? 'on' : ''}
            onClick={() => setTab('login')}
          >
            Login
          </button>
          <button
            type="button"
            className={tab === 'register' ? 'on' : ''}
            onClick={() => setTab('register')}
          >
            Create account
          </button>
        </div>

        {recent.length && tab === 'login' ? (
          <div className="auth-recent">
            <span className="meta">Recent MT5 accounts</span>
            <div className="auth-recent-row">
              {recent.map((a) => (
                <button
                  key={a.code}
                  type="button"
                  className="auth-recent-chip"
                  onClick={() => {
                    setCode(a.code)
                    setAvatar(a.avatar || '')
                    setHint(a.label || a.code)
                    setPassword('')
                  }}
                >
                  <AvatarMark avatar={a.avatar} label={a.label} code={a.code} />
                  <span>
                    <strong>{a.label || a.code}</strong>
                    <em>{a.code}</em>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <form className="auth-form" onSubmit={submit}>
          {tab === 'register' ? (
            <>
              <label>
                First name
                <input
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="e.g. Joel"
                  maxLength={64}
                  autoComplete="given-name"
                  required
                />
              </label>
              <label>
                Last name
                <input
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="e.g. Manalo"
                  maxLength={64}
                  autoComplete="family-name"
                  required
                />
              </label>
              <label>
                Gmail / email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@gmail.com"
                  maxLength={120}
                  autoComplete="email"
                  required
                />
              </label>
              <label>
                MT5 account
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 16))}
                  placeholder="e.g. 25817283"
                  inputMode="numeric"
                  autoComplete="username"
                  required
                />
              </label>
              <label>
                Starting deposit (paper)
                <input
                  type="number"
                  min={50}
                  max={1000000}
                  value={deposit}
                  onChange={(e) => setDeposit(e.target.value)}
                />
              </label>
              <label className="auth-logo-field">
                Logo / avatar (optional)
                <div className="auth-logo-row">
                  <AvatarMark
                    avatar={avatar}
                    label={`${firstName} ${lastName}`.trim()}
                    code={code || '+'}
                  />
                  <input type="file" accept="image/png,image/jpeg,image/webp" onChange={onLogoPick} />
                  {avatar ? (
                    <button type="button" className="btn-ghost" onClick={() => setAvatar('')}>
                      Remove
                    </button>
                  ) : null}
                </div>
              </label>
            </>
          ) : (
            <label>
              MT5 account
              <input
                value={code}
                onChange={(e) => previewCode(e.target.value.replace(/[^\dA-Za-z]/g, '').slice(0, 16))}
                placeholder="e.g. 25817283"
                autoComplete="username"
                required
              />
              {hint ? <span className="meta">{hint}</span> : null}
            </label>
          )}

          <label>
            MT5 password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tab === 'register' ? 'same as your MT5 password' : '••••••••'}
              autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={6}
            />
          </label>

          {error ? <div className="error-banner">{error}</div> : null}

          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Please wait…' : tab === 'login' ? 'Login' : 'Create account'}
          </button>
        </form>

        <p className="meta auth-foot">
          JM FX stores a password hash only (not plain MT5 password for broker login).
          Each MT5 account has its own capital + trade history.
        </p>
      </div>
    </div>
  )
}

export { AvatarMark, fileToDataUrl }
