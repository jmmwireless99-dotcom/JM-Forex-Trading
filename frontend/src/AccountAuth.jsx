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
 * Login / Register gate. Switching accounts only swaps the browser session —
 * server trade journals are never cleared.
 */
export default function AccountAuth({ onAuthed, initialTab = 'login' }) {
  const [tab, setTab] = useState(initialTab === 'register' ? 'register' : 'login')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [label, setLabel] = useState('')
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
    setCode(nextCode)
    const cleaned = String(nextCode || '').trim()
    if (cleaned.length < 4) {
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
        if (!password || password.length < 6) {
          throw new Error('Password must be at least 6 characters')
        }
        const session = await registerAccount({
          label: label || 'Client demo',
          deposit: Number(deposit) || 1000,
          password,
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
          <p>Demo account login — trade history stays with your account code.</p>
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
            Register
          </button>
        </div>

        {recent.length && tab === 'login' ? (
          <div className="auth-recent">
            <span className="meta">Switch account</span>
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
                Display name
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. Joel Desk"
                  maxLength={64}
                  autoComplete="nickname"
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
                  <AvatarMark avatar={avatar} label={label} code="+" />
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
              Account code
              <input
                value={code}
                onChange={(e) => previewCode(e.target.value.toUpperCase())}
                placeholder="e.g. DA4714"
                autoComplete="username"
                required
              />
              {hint ? <span className="meta">{hint}</span> : null}
            </label>
          )}

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tab === 'register' ? 'min 6 characters' : '••••••••'}
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
          Logout / Switch never deletes trades. History stays on your account code + password.
          Use a recent account chip below to switch faster.
        </p>
      </div>
    </div>
  )
}

export { AvatarMark, fileToDataUrl }
