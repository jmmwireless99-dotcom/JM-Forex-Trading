const BASE = (import.meta.env.BASE_URL || '/').replace(/\/?$/, '/')
const API = `${BASE}api`

const ACCOUNT_KEY = 'jm_fx_account'

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
  localStorage.setItem(
    ACCOUNT_KEY,
    JSON.stringify({
      id: session.id,
      token: session.token,
      code: session.code || '',
      label: session.label || '',
    }),
  )
}

export function clearAccountSession() {
  localStorage.removeItem(ACCOUNT_KEY)
}

export function logoutAccount() {
  clearAccountSession()
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
    throw new Error(detail.detail || res.statusText)
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  status: () => request('/status'),
  desk: () => request('/desk'),
  auto: () => request('/auto'),
  mtStatus: () => request('/mt/status'),
  mt4Status: () => request('/mt4/real/status'),
  mt4StatusLegacy: () => request('/mt/status'),
  setExecutionMode: (mode) =>
    request('/execution/mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  candles: (symbol = 'XAUUSD', limit = 200) =>
    request(`/candles?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
  signalCandles: (symbol = 'XAUUSD', limit = 500) =>
    request(`/signal-candles?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
  goldCandles: ({ interval = '5m', limit = 400, days = null } = {}) => {
    const qs = new URLSearchParams({
      interval: String(interval),
      limit: String(limit),
    })
    if (days != null) qs.set('days', String(days))
    return request(`/market/gold-candles?${qs.toString()}`)
  },
  createAccount: (body = {}) =>
    request('/accounts', { method: 'POST', body: JSON.stringify(body) }),
  createScaleInAccount: (body = {}) =>
    request('/accounts/scale-in-demo', { method: 'POST', body: JSON.stringify(body) }),
  loginAccount: ({ code, token }) =>
    request('/accounts/login', {
      method: 'POST',
      body: JSON.stringify({ code: String(code || '').trim(), token: String(token || '').trim() }),
    }),
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
  positions: () => request('/positions'),
  orders: () => request('/orders'),
  trades: (limit = 100) => request(`/trades?limit=${limit}`),
  clearTrades: () => request('/trades/clear', { method: 'POST' }),
  signals: () => request('/signals'),
  aiStatus: () => request('/ai/status'),
  aiAdvice: () => request('/ai/advice'),
  aiHistory: (limit = 50) => request(`/ai/history?limit=${limit}`),
  aiRetrain: () => request('/ai/retrain', { method: 'POST' }),
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

/** Ensure this browser has its own private demo account. */
export async function ensureAccountSession(options = {}) {
  const existing = loadAccountSession()
  if (existing) {
    try {
      const me = await api.accountMe()
      return {
        id: me.account_id || existing.id,
        token: existing.token,
        code: me.account_code || existing.code,
        label: me.account_label || existing.label,
        account: me,
      }
    } catch {
      clearAccountSession()
    }
  }
  const created = await api.createAccount({
    label: options.label || 'Client demo',
    deposit: options.deposit ?? 1000,
    follow_auto: options.follow_auto !== false,
  })
  const session = {
    id: created.account.account_id,
    token: created.token,
    code: created.account.account_code,
    label: created.account.account_label,
  }
  saveAccountSession(session)
  return { ...session, account: created.account, created }
}

export function connectFeed(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  let closed = false
  let ws = null
  let ping = null
  let retry = null
  let attempt = 0

  const connect = () => {
    if (closed) return
    const session = loadAccountSession()
    const qs = session
      ? `?account_id=${encodeURIComponent(session.id)}&account_token=${encodeURIComponent(session.token)}`
      : ''
    const wsPath = `${BASE}api/ws${qs}`.replace(/\/{2,}/g, '/')
    ws = new WebSocket(`${proto}://${window.location.host}${wsPath}`)
    ws.onmessage = (evt) => {
      try {
        onMessage(JSON.parse(evt.data))
      } catch {
        /* ignore malformed */
      }
    }
    ws.onopen = () => {
      attempt = 0
      if (ping) clearInterval(ping)
      ping = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, 15000)
    }
    ws.onclose = () => {
      if (ping) clearInterval(ping)
      ping = null
      if (closed) return
      // Reconnect so late browsers keep receiving desk signals.
      const delay = Math.min(1000 * 2 ** attempt, 15000)
      attempt += 1
      retry = setTimeout(connect, delay)
    }
  }

  connect()
  return () => {
    closed = true
    if (ping) clearInterval(ping)
    if (retry) clearTimeout(retry)
    try {
      ws?.close()
    } catch {
      /* ignore */
    }
  }
}
