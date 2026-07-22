import { useState } from 'react'
import { api, clearAccountSession } from './api'
import { AvatarMark, fileToDataUrl } from './AccountAuth'

/**
 * Profile drawer: logo, rename, change password, logout / switch.
 * None of these actions clear the server trade journal.
 */
export default function AccountProfile({ meta, onUpdated, onLogout }) {
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState(meta?.label || '')
  const [avatar, setAvatar] = useState(meta?.avatar || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  function syncFromMeta() {
    setLabel(meta?.label || '')
    setAvatar(meta?.avatar || '')
    setCurrentPassword('')
    setNewPassword('')
    setNote('')
    setError('')
  }

  async function saveProfile(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNote('')
    try {
      const res = await api.updateProfile({
        label: label.trim() || meta?.label,
        avatar: avatar || '',
      })
      onUpdated?.({
        id: res.account.account_id,
        code: res.account.account_code,
        label: res.account.account_label,
        avatar: res.account.avatar || '',
        has_password: res.account.has_password,
      })
      setNote(res.message || 'Profile saved — history kept.')
    } catch (err) {
      setError(err.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  async function savePassword(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNote('')
    try {
      const body = { new_password: newPassword }
      if (meta?.has_password) body.current_password = currentPassword
      const res = await api.changePassword(body)
      onUpdated?.({
        ...meta,
        has_password: true,
      })
      setCurrentPassword('')
      setNewPassword('')
      setNote(res.message || 'Password updated — history kept.')
    } catch (err) {
      setError(err.message || 'Password change failed')
    } finally {
      setBusy(false)
    }
  }

  async function onLogoPick(e) {
    try {
      const data = await fileToDataUrl(e.target.files?.[0])
      setAvatar(data)
      setError('')
    } catch (err) {
      setError(err.message || 'Logo failed')
    }
  }

  function logout() {
    clearAccountSession()
    onLogout?.()
  }

  return (
    <div className="acct-profile">
      <button
        type="button"
        className="acct-profile-trigger"
        onClick={() => {
          syncFromMeta()
          setOpen((v) => !v)
        }}
      >
        <AvatarMark avatar={meta?.avatar} label={meta?.label} code={meta?.code} />
        <span className="acct-profile-text">
          <strong>{meta?.label || 'Demo'}</strong>
          <em>{meta?.code || '—'}</em>
        </span>
      </button>

      {open ? (
        <div className="acct-profile-panel" role="dialog" aria-label="Account profile">
          <div className="acct-profile-head">
            <h3>Account profile</h3>
            <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <p className="meta">
            Code <code>{meta?.code}</code> — logout / switch / rename / password never wipe trade
            history.
          </p>

          <form className="acct-form" onSubmit={saveProfile}>
            <label className="auth-logo-field">
              Logo
              <div className="auth-logo-row">
                <AvatarMark avatar={avatar} label={label} code={meta?.code} />
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={onLogoPick} />
                {avatar ? (
                  <button type="button" className="btn-ghost" onClick={() => setAvatar('')}>
                    Remove
                  </button>
                ) : null}
              </div>
            </label>
            <label>
              Display name
              <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={64} />
            </label>
            <button type="submit" className="btn-primary" disabled={busy}>
              Save profile
            </button>
          </form>

          <form className="acct-form" onSubmit={savePassword}>
            <h4>{meta?.has_password ? 'Change password' : 'Set password'}</h4>
            {meta?.has_password ? (
              <label>
                Current password
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </label>
            ) : (
              <p className="meta">Set a password so you can login / switch devices later.</p>
            )}
            <label>
              New password
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={6}
                autoComplete="new-password"
                required
              />
            </label>
            <button type="submit" className="btn-ghost" disabled={busy}>
              {meta?.has_password ? 'Update password' : 'Set password'}
            </button>
          </form>

          {error ? <div className="error-banner">{error}</div> : null}
          {note ? <div className="ok-banner">{note}</div> : null}

          <div className="acct-profile-actions">
            <button type="button" className="btn-ghost" disabled={busy} onClick={logout}>
              Logout / switch account
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
