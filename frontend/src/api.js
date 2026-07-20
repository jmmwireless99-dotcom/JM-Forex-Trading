const BASE = (import.meta.env.BASE_URL || '/').replace(/\/?$/, '/')
const API = `${BASE}api`

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
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
  mtStatus: () => request('/mt/status'),
  mt4Status: () => request('/mt/status'),
  setExecutionMode: (mode) =>
    request('/execution/mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  candles: (symbol = 'XAUUSD', limit = 200) =>
    request(`/candles?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
  account: () => request('/account'),
  positions: () => request('/positions'),
  orders: () => request('/orders'),
  trades: (limit = 100) => request(`/trades?limit=${limit}`),
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
  placeOrder: (body) =>
    request('/orders', { method: 'POST', body: JSON.stringify(body) }),
  closePosition: (id) =>
    request(`/positions/${id}/close`, { method: 'POST' }),
}

export function connectFeed(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsPath = `${BASE}api/ws`.replace(/\/{2,}/g, '/')
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
