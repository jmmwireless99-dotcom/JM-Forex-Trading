/** Read-only calls to the production JM FX API (no writes to the trading desk). */

const API_BASE = (import.meta.env.VITE_JM_API || '/fx/api').replace(/\/$/, '')

async function request(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export const labApi = {
  desk: () => request('/desk'),
  status: () => request('/status'),
  auto: () => request('/auto'),
  goldCandles: (interval = '5', limit = 120) =>
    request(`/market/gold-candles?interval=${encodeURIComponent(interval)}&limit=${limit}`),
}

export { API_BASE }
