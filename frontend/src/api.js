const API = '/api'

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
  account: () => request('/account'),
  positions: () => request('/positions'),
  orders: () => request('/orders'),
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
  const ws = new WebSocket(`${proto}://${window.location.host}/api/ws`)
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