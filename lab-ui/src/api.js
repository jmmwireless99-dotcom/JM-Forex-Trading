/** JM Lab trading API (isolated demo backend). */

const LAB_API = (import.meta.env.VITE_LAB_API || '/lab/api').replace(/\/$/, '')
const JM_FX_API = (import.meta.env.VITE_JM_API || '/fx/api').replace(/\/$/, '')

const SESSION_KEY = 'jm_lab_trade_session'
const SUITE_KEY = 'jm_lab_pair_suite'

let _activePair = null

export function setLabSessionPair(pair) {
  _activePair = pair ? String(pair).toUpperCase() : null
}

export function getLabSessionPair() {
  return _activePair
}

function sessionStorageKey(pair) {
  const sym = pair ?? _activePair
  return sym ? `${SESSION_KEY}_${sym}` : SESSION_KEY
}

export function loadLabSession(pair) {
  try {
    return JSON.parse(localStorage.getItem(sessionStorageKey(pair)) || 'null')
  } catch {
    return null
  }
}

export function saveLabSession(session, pair) {
  const key = sessionStorageKey(pair)
  if (!session) {
    localStorage.removeItem(key)
    return
  }
  localStorage.setItem(key, JSON.stringify(session))
}

export function loadPairSuite() {
  try {
    return JSON.parse(localStorage.getItem(SUITE_KEY) || 'null')
  } catch {
    return null
  }
}

export function savePairSuite(suite) {
  if (!suite) {
    localStorage.removeItem(SUITE_KEY)
    return
  }
  localStorage.setItem(SUITE_KEY, JSON.stringify(suite))
}

async function labRequest(path, options = {}) {
  return labRequestAs(null, path, options)
}

async function labRequestAs(session, path, options = {}) {
  const active = session || loadLabSession()
  const headers = {
    Accept: 'application/json',
    ...(options.headers || {}),
  }
  if (active?.account_id && active?.token) {
    headers['X-JM-Lab-Account-Id'] = active.account_id
    headers['X-JM-Lab-Account-Token'] = active.token
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

export function isInvalidLabSessionError(err) {
  const msg = String(err?.message || err || '')
  return msg.includes('Invalid lab account session') || msg.includes('Missing X-JM-Lab-Account-Id')
}

function mapSuiteAccounts(res) {
  return (res.accounts || []).map((a) => ({
    symbol: a.symbol,
    account_id: a.account_id,
    code: a.code,
    token: a.token,
    label: a.label,
    strategy: a.strategy,
  }))
}

export async function syncPairSuiteFromServer(startAuto = false) {
  const res = await labTradeApi.createPairSuite(10000, startAuto)
  const accounts = mapSuiteAccounts(res)
  if (accounts.length) {
    savePairSuite({ accounts, created_at: new Date().toISOString() })
  }
  return { accounts, message: res.message }
}

async function validateLabSession(session) {
  await labTradeApi.account(session)
  return true
}

export async function ensurePairAccount(symbol) {
  const sym = String(symbol).toUpperCase()

  async function pickFromServer(startAuto = false) {
    const res = await labTradeApi.createPairSuite(10000, startAuto)
    const accounts = mapSuiteAccounts(res)
    if (accounts.length) {
      savePairSuite({ accounts, created_at: new Date().toISOString() })
    }
    const row = accounts.find((a) => a.symbol === sym)
    if (!row) throw new Error(`No demo account for ${sym}`)
    return {
      account_id: row.account_id,
      token: row.token,
      code: row.code,
      symbol: sym,
    }
  }

  const candidates = []
  const perPair = loadLabSession(sym)
  if (perPair?.account_id && perPair?.token) candidates.push({ ...perPair, symbol: sym })
  const suite = loadPairSuite()
  const cached = suite?.accounts?.find((a) => a.symbol === sym)
  if (cached?.account_id && cached?.token) {
    candidates.push({
      account_id: cached.account_id,
      token: cached.token,
      code: cached.code,
      symbol: sym,
    })
  }

  for (const row of candidates) {
    try {
      await validateLabSession(row)
      return row
    } catch (e) {
      if (!isInvalidLabSessionError(e)) throw e
    }
  }

  return pickFromServer(false)
}

export const labTradeApi = {
  health: () => labRequest('/health'),
  symbols: () => labRequest('/symbols'),
  ticks: (symbol) =>
    symbol
      ? labRequest(`/ticks?symbol=${encodeURIComponent(symbol)}`)
      : labRequest('/ticks'),
  quote: (symbol, fresh = false) =>
    labRequest(`/quote?symbol=${encodeURIComponent(symbol)}${fresh ? '&fresh=1' : ''}`),
  candles: (symbol, interval = '5', limit = 120) =>
    labRequest(`/candles?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`),
  createAccount: (deposit = 10000, label = 'Lab demo') =>
    labRequest('/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deposit, label }),
    }),
  createPairSuite: (deposit = 10000, startAuto = true) =>
    labRequest('/accounts/pair-suite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deposit, start_auto: startAuto }),
    }),
  account: (session) => labRequestAs(session, '/account'),
  positions: (session) => labRequestAs(session, '/positions'),
  trades: (session) => labRequestAs(session, '/trades'),
  auto: (session) => labRequestAs(session, '/auto'),
  marketOrder: (body) =>
    labRequest('/orders/market', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  closePosition: (id) =>
    labRequest(`/positions/${encodeURIComponent(id)}/close`, { method: 'POST' }),
  updatePositionStops: (id, body, session) =>
    labRequestAs(session, `/positions/${encodeURIComponent(id)}/stops`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  setAuto: (body, session) =>
    labRequestAs(session, '/auto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  syncAutoPreset: (session) =>
    labRequestAs(session, '/auto/sync-preset', { method: 'POST' }),
  setAutoFor: (session, body) => labTradeApi.setAuto(body, session),
  strategies: () => labRequest('/strategies'),
  suiteStatus: () => labRequest('/suite/status'),
}

export const labApi = {
  desk: () => fxRequest('/desk'),
  status: () => fxRequest('/status'),
  auto: () => fxRequest('/auto'),
  goldCandles: (interval = '5', limit = 120) =>
    fxRequest(`/market/gold-candles?interval=${encodeURIComponent(interval)}&limit=${limit}`),
}

export { LAB_API, JM_FX_API }
