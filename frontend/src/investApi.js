const BASE = (import.meta.env.BASE_URL || '/').replace(/\/?$/, '/')
const API = `${BASE}api`

const AUTH_KEY = 'jm_fx_invest_auth'
const INVEST_KEY = 'jm_fx_investment'

export function loadAuthSession() {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed?.auth_token && parsed?.user) return parsed
  } catch {
    /* ignore */
  }
  return null
}

export function saveAuthSession(session) {
  if (!session?.auth_token || !session?.user) return
  localStorage.setItem(
    AUTH_KEY,
    JSON.stringify({
      auth_token: session.auth_token,
      user: session.user,
      account_id: session.account_id,
      account_token: session.account_token,
    }),
  )
  if (session.account_id && session.account_token) {
    localStorage.setItem(
      INVEST_KEY,
      JSON.stringify({
        id: session.account_id,
        token: session.account_token,
        code: session.account?.account_code || '',
        label: session.account?.account_label || session.user.full_name,
      }),
    )
  }
}

export function clearAuthSession() {
  localStorage.removeItem(AUTH_KEY)
  localStorage.removeItem(INVEST_KEY)
}

export function loadInvestSession() {
  try {
    const raw = localStorage.getItem(INVEST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed?.id && parsed?.token) return parsed
  } catch {
    /* ignore */
  }
  return null
}

function authHeaders() {
  const session = loadAuthSession()
  if (!session?.auth_token) return {}
  return { Authorization: `Bearer ${session.auth_token}` }
}

function investHeaders() {
  const invest = loadInvestSession()
  const headers = { ...authHeaders() }
  if (invest?.id && invest?.token) {
    headers['X-JM-Invest-Id'] = invest.id
    headers['X-JM-Invest-Token'] = invest.token
  }
  return headers
}

async function investRequest(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...investHeaders(),
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || res.statusText)
  }
  return res.json()
}

export const investApi = {
  register: (email, password, fullName, referralCode) =>
    investRequest('/investment/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        referral_code: referralCode || undefined,
      }),
    }),
  login: (email, password) =>
    investRequest('/investment/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => investRequest('/investment/auth/me'),
  account: () => investRequest('/investment/accounts/me'),
  cashIn: (amount, note) =>
    investRequest('/investment/cash-in', {
      method: 'POST',
      body: JSON.stringify({ amount: Number(amount), note }),
    }),
  cashOut: (amount, note) =>
    investRequest('/investment/cash-out', {
      method: 'POST',
      body: JSON.stringify({ amount: Number(amount), note }),
    }),
  adminStats: () => investRequest('/investment/admin/stats'),
  adminAccounts: () => investRequest('/investment/admin/accounts'),
  referrals: () => investRequest('/investment/referrals/me'),
}

export function isAdmin() {
  return loadAuthSession()?.user?.role === 'admin'
}

export function logoutInvest() {
  clearAuthSession()
}

export async function refreshAuthSession() {
  const existing = loadAuthSession()
  if (!existing) return null
  try {
    const res = await investApi.me()
    return { ...existing, user: res.user, account: res.account }
  } catch {
    clearAuthSession()
    return null
  }
}
