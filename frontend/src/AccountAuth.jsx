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
 * Default = paper demo. Optional: link live MT5 login (e.g. Joel) for bridge sync.
 */
export default function AccountAuth({ onAuthed, initialTab = 'login' }) {
  const [tab, setTab] = useState(initialTab === 'register' ? 'register' : 'login')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [label, setLabel] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [deposit, setDeposit] = useState('1000')
  const [linkMt5, setLinkMt5] = useState(false)
  const [mtPlatform, setMtPlatform] = useState('mt5')
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
      } else if (linkMt5) {
        const mt5 = String(code || '').trim()
        if (!/^\d{5,16}$/.test(mt5)) {
          throw new Error('MT5 account must be 5–16 digits')
        }
        if (!password || password.length < 6) {
          throw new Error('MT5 password must be at least 6 characters')
        }
        if (!firstName.trim() || !lastName.trim()) {
          throw new Error('First name and last name are required for MT5 link')
        }
        if (!email.trim() || !email.includes('@')) {
          throw new Error('Gmail / email is required for MT5 link')
        }
        const session = await registerAccount({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          mt5_login: mt5,
          mt_platform: mtPlatform === 'mt4' ? 'mt4' : 'mt5',
          password,
          avatar: avatar || undefined,
        })
        onAuthed(session)
      } else {
        if (!password || password.length < 6) {
          throw new Error('Password must be at least 6 characters')
        }
        const amount = Number(deposit)
        if (!Number.isFinite(amount) || amount < 50) {
          throw new Error('Paper deposit must be at least 50')
        }
        const session = await registerAccount({
          label: label.trim() || undefined,
          deposit: amount,
          password,
          avatar: avatar || undefined,
          first_name: firstName.trim() || undefined,
          last_name: lastName.trim() || undefined,
          email: email.trim() || undefined,
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
            Default accounts are <strong>paper demo</strong>. Link an MT5 login only if
            you want live terminal sync (one bridge terminal at a time).
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
            <span className="meta">Recent accounts</span>
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
              <label className="auth-check">
                <input
                  type="checkbox"
                  checked={linkMt5}
                  onChange={(e) => {
                    setLinkMt5(e.target.checked)
                    setError('')
                  }}
                />
                <span>Link live MT4/MT5 account (optional — not for paper demos)</span>
              </label>

              {linkMt5 ? (
                <>
                  <label>
                    Platform
                    <select
                      value={mtPlatform}
                      onChange={(e) => setMtPlatform(e.target.value)}
                      required
                    >
                      <option value="mt5">MT5 only (Joel Madera)</option>
                      <option value="mt4">MT4 — bagong/hiwalay na account</option>
                    </select>
                  </label>
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
                      placeholder="e.g. Madera"
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
                    MT4 / MT5 account
                    <input
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 16))}
                      placeholder={mtPlatform === 'mt4' ? 'MT4 login number' : 'e.g. 25817283'}
                      inputMode="numeric"
                      autoComplete="username"
                      required
                    />
                  </label>
                  <p className="meta">
                    JOEL MADERA = MT5 only (walang MT4 sa account niya).
                    Para sa MT4, gumawa ng bagong JM FX account — Platform MT4.
                  </p>
                </>
              ) : (
                <>
                  <label>
                    Display name (optional)
                    <input
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      placeholder="e.g. Demo Desk"
                      maxLength={64}
                      autoComplete="nickname"
                    />
                  </label>
                  <label>
                    Paper deposit (USD)
                    <input
                      type="number"
                      min={50}
                      max={1000000}
                      step={50}
                      value={deposit}
                      onChange={(e) => setDeposit(e.target.value)}
                      required
                    />
                  </label>
                  <p className="meta">
                    Paper capital + trades are private to this account. Save the account
                    code you get after create.
                  </p>
                </>
              )}

              <label className="auth-logo-field">
                Logo / avatar (optional)
                <div className="auth-logo-row">
                  <AvatarMark
                    avatar={avatar}
                    label={label || `${firstName} ${lastName}`.trim()}
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
              Account code / MT5 login
              <input
                value={code}
                onChange={(e) => previewCode(e.target.value.replace(/[^\dA-Za-z]/g, '').slice(0, 16))}
                placeholder="paper code or MT5 number"
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
              placeholder={
                tab === 'register' && linkMt5
                  ? 'same as your MT5 password'
                  : '••••••••'
              }
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
          MT5 sync needs Windows agent + JM_Forex_Bridge EA on the matching terminal.
          Paper accounts never use that terminal.
        </p>
      </div>
    </div>
  )
}

export { AvatarMark, fileToDataUrl }
