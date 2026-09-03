/** Path-based pair URLs: /lab/EURUSD, /lab/audnzd, etc. */

export const PAIR_URL_SYMBOLS = ['EURUSD', 'AUDNZD', 'EURCHF', 'XAUUSD']

export function normalizePairSymbol(raw) {
  const sym = String(raw || '').toUpperCase().replace(/[^A-Z]/g, '')
  return PAIR_URL_SYMBOLS.includes(sym) ? sym : null
}

/** Read pair from pathname e.g. /lab/EURUSD → EURUSD */
export function parsePairFromPath(pathname = window.location.pathname) {
  const parts = pathname.replace(/\/+$/, '').split('/').filter(Boolean)
  const labIdx = parts.findIndex((p) => p.toLowerCase() === 'lab')
  if (labIdx === -1 || labIdx + 1 >= parts.length) return null
  const segment = parts[labIdx + 1]
  if (!segment || segment.includes('.')) return null
  return normalizePairSymbol(segment)
}

export function pairTradePath(symbol) {
  const base = (import.meta.env.BASE_URL || '/lab/').replace(/\/$/, '')
  return `${base}/${String(symbol).toUpperCase()}`
}

export function pairTradeUrl(symbol) {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}${pairTradePath(symbol)}`
  }
  return pairTradePath(symbol)
}
