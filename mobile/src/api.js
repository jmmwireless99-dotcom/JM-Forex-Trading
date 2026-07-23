import Constants from 'expo-constants'
import AsyncStorage from '@react-native-async-storage/async-storage'

const DEFAULT_API = 'https://jmtechsolution.cloud/fx/api'
const STORAGE_KEY = 'jm_forex_api_base'

export function defaultApiBase() {
  return Constants.expoConfig?.extra?.apiBase || DEFAULT_API
}

export async function getApiBase() {
  const saved = await AsyncStorage.getItem(STORAGE_KEY)
  return (saved || defaultApiBase()).replace(/\/$/, '')
}

export async function setApiBase(url) {
  const clean = String(url || defaultApiBase()).trim().replace(/\/$/, '')
  await AsyncStorage.setItem(STORAGE_KEY, clean)
  return clean
}

async function request(path, options = {}) {
  const base = await getApiBase()
  const res = await fetch(`${base}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || res.statusText || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  status: () => request('/status'),
  desk: () => request('/desk'),
  auto: () => request('/auto'),
  account: () => request('/account'),
  positions: () => request('/positions'),
  trades: (limit = 40) => request(`/trades?limit=${limit}`),
  ticks: () => request('/ticks'),
  strategies: () => request('/strategies'),
  recommended: () => request('/strategies/recommended'),
  setStrategy: (name) =>
    request('/strategies/active', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  autoTransfer: () => request('/strategies/auto-transfer', { method: 'POST' }),
  start: (strategy) =>
    request('/engine/start', {
      method: 'POST',
      body: JSON.stringify(strategy ? { strategy } : {}),
    }),
  stop: () => request('/engine/stop', { method: 'POST' }),
}
