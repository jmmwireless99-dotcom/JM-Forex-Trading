/** Pip math for lab FX (0.0001) and gold XAUUSD (0.01). */

export function pipSize(sym) {
  return sym === 'XAUUSD' ? 0.01 : 0.0001
}

export function pipsFromEntryPrice(sym, side, entry, price, kind) {
  const pip = pipSize(sym)
  const e = Number(entry)
  const p = Number(price)
  if (!Number.isFinite(e) || !Number.isFinite(p)) return null
  let dist
  if (kind === 'sl') {
    dist = side === 'BUY' ? e - p : p - e
  } else {
    dist = side === 'BUY' ? p - e : e - p
  }
  if (dist < 0) return null
  return Math.round(dist / pip)
}

export function pricesFromEntryPips(sym, side, entry, slPips, tpPips) {
  const pip = pipSize(sym)
  const e = Number(entry)
  const sl = Number(slPips) * pip
  const tp = Number(tpPips) * pip
  if (!Number.isFinite(e)) return null
  if (side === 'BUY') {
    return { stop_loss: e - sl, take_profit: e + tp }
  }
  return { stop_loss: e + sl, take_profit: e - tp }
}

export function positionStopPips(position) {
  if (!position) return { sl: null, tp: null }
  const sl =
    position.stop_loss != null
      ? pipsFromEntryPrice(position.symbol, position.side, position.entry_price, position.stop_loss, 'sl')
      : null
  const tp =
    position.take_profit != null
      ? pipsFromEntryPrice(position.symbol, position.side, position.entry_price, position.take_profit, 'tp')
      : null
  return { sl, tp }
}
