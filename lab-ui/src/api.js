/** JM Lab trading API (isolated demo backend). */

const LAB_API = (import.meta.env.VITE_LAB_API || '/lab/api').replace(/\/$/, '')
const JM_FX_API = (import.meta.env.VITE_JM_API || '/fx/api').replace(/\/$/, '')

const SESSION_KEY = 'jm_lab_trade_session'

export function loadLabSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
  } catch {
    return null
  }
}

export function saveLabSession(session) {
  if (!session) {
    localStorage.removeItem(SESSION_KEY)
    return
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

async function labRequest(path, options = {}) {
  const session = loadLabSession()
  const headers = {
    Accept: 'application/json',
    ...(options.headers || {}),
  }
  if (session?.account_id && session?.token) {
    headers['X-JM-Lab-Account-Id'] = session.account_id
    headers['X-JM-Lab-Account-Token'] = session.token
  }
  const res = await fetch(`${LAB_API}${path}`, { ...options, headers })
  if (!res.ok) {
    let msg = await res.text()
    try {
      const j = JSON.parse(msg)
      msg = j.detail || j.message || msg
    } catch {
      /* plain text */
    }
    throw new Error(msg || `HTTP ${res.status}`)
  }
  return res.json()
}

async function fxRequest(path) {
  const res = await fetch(`${JM_FX_API}${path}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export const labTradeApi = {
  health: () => labRequest('/health'),
  symbols: () => labRequest('/symbols'),
  ticks: () => labRequest('/ticks'),
  candles: (symbol, interval = '5', limit = 120) =>
    labRequest(`/candles?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`),
  createAccount: (deposit = 10000, label = 'Lab demo') =>
    labRequest('/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deposit, label }),
    }),
  account: () => labRequest('/account'),
  positions: () => labRequest('/positions'),
  trades: () => labRequest('/trades'),
  marketOrder: (body) =>
    labRequest('/orders/market', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  closePosition: (id) =>
    labRequest(`/positions/${encodeURIComponent(id)}/close`, { method: 'POST' }),
}

export const labApi = {
  desk: () => fxRequest('/desk'),
  status: () => fxRequest('/status'),
  auto: () => fxRequest('/auto'),
  goldCandles: (interval = '5', limit = 120) =>
    fxRequest(`/market/gold-candles?interval=${encodeURIComponent(interval)}&limit=${limit}`),
}

export { LAB_API, JM_FX_API }
