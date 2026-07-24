const BASE = (import.meta.env.BASE_URL || '/').replace(/\/?$/, '/')
const API = `${BASE}api`

const ACCOUNT_KEY = 'jm_fx_account'
const RECENT_KEY = 'jm_fx_recent_accounts'

export function loadAccountSession() {
  try {
    const raw = localStorage.getItem(ACCOUNT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed?.id && parsed?.token) return parsed
  } catch {
    /* ignore */
  }
  return null
}

export function saveAccountSession(session) {
  if (!session?.id || !session?.token) return
  const payload = {
    id: session.id,
    token: session.token,
    code: session.code || '',
    label: session.label || '',
    avatar: session.avatar || '',
  }
  localStorage.setItem(ACCOUNT_KEY, JSON.stringify(payload))
  rememberRecentAccount(payload)
}

export function clearAccountSession() {
  localStorage.removeItem(ACCOUNT_KEY)
}

export function loadRecentAccounts() {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function rememberRecentAccount(session) {
  if (!session?.code) return
  const next = [
    {
      code: session.code,
      label: session.label || '',
      avatar: session.avatar || '',
    },
    ...loadRecentAccounts().filter((a) => a.code !== session.code),
  ].slice(0, 8)
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}

function accountHeaders() {
  const session = loadAccountSession()
  if (!session) return {}
  return {
    'X-JM-Account-Id': session.id,
    'X-JM-Account-Token': session.token,
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...accountHeaders(),
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    const err = new Error(detail.detail || res.statusText || `HTTP ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function sessionFromAuthResponse(res) {
  const account = res.account || {}
  return {
    id: account.account_id,
    token: res.token,
    code: account.account_code,
    label: account.account_label,
    avatar: account.avatar || '',
    account,
    capital: res.capital,
    trades: res.trades,
    message: res.message,
  }
}

export const api = {
  health: () => request('/health'),
  status: () => request('/status'),
  desk: () => request('/desk'),
  auto: () => request('/auto'),
  mtStatus: () => request('/mt/status'),
  mt4Status: () => request('/mt/status'),
  setExecutionMode: (mode) =>
    request('/execution/mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  candles: (symbol = 'XAUUSD', limit = 200) =>
    request(`/candles?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
  goldCandles: ({ interval = '5m', limit = 400 } = {}) =>
    request(
      `/market/gold-candles?interval=${encodeURIComponent(interval)}&limit=${encodeURIComponent(limit)}`,
    ),
  btcCandles: ({ interval = '5m', limit = 400 } = {}) =>
    request(
      `/market/btc-candles?interval=${encodeURIComponent(interval)}&limit=${encodeURIComponent(limit)}`,
    ),
  createAccount: (body = {}) =>
    request('/accounts', { method: 'POST', body: JSON.stringify(body) }),
  loginAccount: (body) =>
    request('/accounts/login', { method: 'POST', body: JSON.stringify(body) }),
  lookupAccount: (code) => request(`/accounts/lookup/${encodeURIComponent(code)}`),
  updateProfile: (body) =>
    request('/accounts/me', { method: 'PATCH', body: JSON.stringify(body) }),
  changePassword: (body) =>
    request('/accounts/me/password', { method: 'POST', body: JSON.stringify(body) }),
  accountMe: () => request('/accounts/me'),
  account: () => request('/account'),
  capitalPreview: (amount) =>
    request(
      amount != null
        ? `/account/capital?amount=${encodeURIComponent(amount)}`
        : '/account/capital',
    ),
  setDeposit: (amount, reset = true) =>
    request('/account/deposit', {
      method: 'POST',
      body: JSON.stringify({ amount: Number(amount), reset }),
    }),
  setTradeSettings: (body) =>
    request('/account/settings', { method: 'POST', body: JSON.stringify(body) }),
  positions: () => request('/positions'),
  orders: () => request('/orders'),
  trades: (limit = 100) => request(`/trades?limit=${limit}`),
  clearTrades: () => request('/trades/clear', { method: 'POST' }),
  signals: () => request('/signals'),
  ticks: () => request('/ticks'),
  strategies: () => request('/strategies'),
  start: (strategy) =>
    request('/engine/start', {
      method: 'POST',
      body: JSON.stringify(strategy ? { strategy } : {}),
    }),
  stop: () => request('/engine/stop', { method: 'POST' }),
  setStrategy: (name) =>
    request('/strategies/active', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  recommended: () => request('/strategies/recommended'),
  autoTransfer: () =>
    request('/strategies/auto-transfer', { method: 'POST' }),
  placeOrder: (body) =>
    request('/orders', { method: 'POST', body: JSON.stringify(body) }),
  closePosition: (id) =>
    request(`/positions/${id}/close`, { method: 'POST' }),
  setStops: (id, body) =>
    request(`/positions/${id}/stops`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

/** Restore existing browser session only — never auto-creates a new empty account. */
export async function restoreAccountSession() {
  const existing = loadAccountSession()
  if (!existing) return null
  let lastErr = null
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const me = await api.accountMe()
      const session = {
        id: me.account_id || existing.id,
        token: existing.token,
        code: me.account_code || existing.code,
        label: me.account_label || existing.label,
        avatar: me.avatar || existing.avatar || '',
        account: me,
      }
      saveAccountSession(session)
      return session
    } catch (err) {
      lastErr = err
      const status = err?.status
      if (status === 401 || status === 403 || status === 404) {
        clearAccountSession()
        return null
      }
      await sleep(400 * (attempt + 1))
    }
  }
  if (loadAccountSession()) {
    throw lastErr || new Error('Account session temporarily unavailable')
  }
  return null
}

export async function registerAccount(options = {}) {
  const created = await api.createAccount({
    label: options.label,
    deposit: options.deposit ?? 1000,
    follow_auto: options.follow_auto !== false,
    password: options.password,
    avatar: options.avatar || undefined,
    first_name: options.first_name,
    last_name: options.last_name,
    email: options.email,
    mt5_login: options.mt5_login,
    mt_platform: options.mt_platform,
  })
  const session = sessionFromAuthResponse(created)
  saveAccountSession(session)
  return { ...session, created: true, message: created.message }
}

export async function loginAccount({ code, password }) {
  const res = await api.loginAccount({ code: String(code || '').trim(), password })
  const session = sessionFromAuthResponse(res)
  saveAccountSession(session)
  return { ...session, message: res.message }
}

/** @deprecated use restoreAccountSession + register/login — kept for older callers */
export async function ensureAccountSession(options = {}) {
  const restored = await restoreAccountSession()
  if (restored) return restored
  return registerAccount(options)
}

export function connectFeed(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const session = loadAccountSession()
  const qs = session
    ? `?account_id=${encodeURIComponent(session.id)}&account_token=${encodeURIComponent(session.token)}`
    : ''
  const wsPath = `${BASE}api/ws${qs}`.replace(/\/{2,}/g, '/')
  const ws = new WebSocket(`${proto}://${window.location.host}${wsPath}`)
  ws.onmessage = (evt) => {
    try {
      onMessage(JSON.parse(evt.data))
    } catch {
      /* ignore malformed */
    }
  }
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send('ping')
  }, 15000)
  ws.onclose = () => clearInterval(ping)
  return () => {
    clearInterval(ping)
    ws.close()
  }
}
