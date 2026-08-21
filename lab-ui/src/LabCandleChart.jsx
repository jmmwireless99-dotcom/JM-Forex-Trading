import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { labTradeApi } from './api.js'
import { pipsFromEntryPrice } from './pips.js'

const RANGES = [
  { id: '5', label: 'M5' },
  { id: '15', label: 'M15' },
  { id: '60', label: 'H1' },
]

const DRAG_HIT_PX = 12

function toChartCandle(c) {
  const t = Number(c.time)
  return {
    time: t,
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }
}

function priceFormat(symbol) {
  if (symbol === 'XAUUSD') {
    return { type: 'price', precision: 2, minMove: 0.01 }
  }
  return { type: 'price', precision: 5, minMove: 0.00001 }
}

function fmtLive(symbol, n) {
  const d = symbol === 'XAUUSD' ? 2 : 5
  return Number(n).toFixed(d)
}

function roundPrice(symbol, n) {
  const d = symbol === 'XAUUSD' ? 2 : 5
  return Number(Number(n).toFixed(d))
}

function emaSeries(closes, period) {
  if (!closes.length) return []
  const k = 2 / (period + 1)
  const out = new Array(closes.length).fill(null)
  if (closes.length < period) return out
  let sum = 0
  for (let i = 0; i < period; i += 1) sum += closes[i]
  let prev = sum / period
  out[period - 1] = prev
  for (let i = period; i < closes.length; i += 1) {
    prev = closes[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

function validStopPrice(side, entry, price, kind) {
  if (!Number.isFinite(price)) return false
  if (side === 'BUY') {
    return kind === 'sl' ? price < entry : price > entry
  }
  return kind === 'sl' ? price > entry : price < entry
}

export default function LabCandleChart({
  symbol = 'EURUSD',
  livePrice = null,
  positions = [],
  onUpdateStops = null,
}) {
  const hostRef = useRef(null)
  const wrapRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const ema20Ref = useRef(null)
  const ema50Ref = useRef(null)
  const stopLinesRef = useRef({ entry: null, sl: null, tp: null })
  const liveLineRef = useRef(null)
  const displayRowsRef = useRef([])
  const posMetaRef = useRef(null)
  const dragRef = useRef({ kind: null, startPrice: null })

  const [range, setRange] = useState('5')
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('idle')
  const [err, setErr] = useState('')
  const [liveAt, setLiveAt] = useState(null)
  const [dragHint, setDragHint] = useState('')
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  const openPos = useMemo(
    () => (positions || []).filter((p) => (p.status || 'OPEN').toUpperCase() === 'OPEN'),
    [positions],
  )

  const activePos = useMemo(
    () => openPos.find((p) => p.symbol === symbol) || null,
    [openPos, symbol],
  )

  const editable = Boolean(onUpdateStops && activePos)

  const syncStopLines = useCallback(
    (p) => {
      const series = seriesRef.current
      if (!series || !p) return
      const lines = stopLinesRef.current
      const slPips =
        p.stop_loss != null
          ? pipsFromEntryPrice(symbol, p.side, p.entry_price, p.stop_loss, 'sl')
          : null
      const tpPips =
        p.take_profit != null
          ? pipsFromEntryPrice(symbol, p.side, p.entry_price, p.take_profit, 'tp')
          : null
      const slTitle =
        p.stop_loss != null
          ? `SL ${fmtLive(symbol, p.stop_loss)}${slPips != null ? ` · ${slPips}p` : ''}`
          : 'SL'
      const tpTitle =
        p.take_profit != null
          ? `TP ${fmtLive(symbol, p.take_profit)}${tpPips != null ? ` · ${tpPips}p` : ''}`
          : 'TP'
      const entryTitle = `${p.side} @ ${fmtLive(symbol, p.entry_price)}`

      if (!lines.entry) {
        lines.entry = series.createPriceLine({
          price: Number(p.entry_price),
          color: p.side === 'BUY' ? '#6ee7b7' : '#f87171',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: entryTitle,
        })
      } else {
        lines.entry.applyOptions({
          price: Number(p.entry_price),
          color: p.side === 'BUY' ? '#6ee7b7' : '#f87171',
          title: entryTitle,
        })
      }

      if (p.stop_loss != null) {
        if (!lines.sl) {
          lines.sl = series.createPriceLine({
            price: Number(p.stop_loss),
            color: '#f87171',
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: slTitle,
          })
        } else {
          lines.sl.applyOptions({ price: Number(p.stop_loss), title: slTitle })
        }
      } else if (lines.sl) {
        series.removePriceLine(lines.sl)
        lines.sl = null
      }

      if (p.take_profit != null) {
        if (!lines.tp) {
          lines.tp = series.createPriceLine({
            price: Number(p.take_profit),
            color: '#6ee7b7',
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: tpTitle,
          })
        } else {
          lines.tp.applyOptions({ price: Number(p.take_profit), title: tpTitle })
        }
      } else if (lines.tp) {
        series.removePriceLine(lines.tp)
        lines.tp = null
      }

      posMetaRef.current = {
        id: p.id,
        side: p.side,
        entry_price: Number(p.entry_price),
        stop_loss: p.stop_loss != null ? Number(p.stop_loss) : null,
        take_profit: p.take_profit != null ? Number(p.take_profit) : null,
      }
    },
    [symbol],
  )

  const clearStopLines = useCallback(() => {
    const series = seriesRef.current
    if (!series) return
    const lines = stopLinesRef.current
    for (const key of ['entry', 'sl', 'tp']) {
      if (lines[key]) {
        try {
          series.removePriceLine(lines[key])
        } catch {
          /* ignore */
        }
        lines[key] = null
      }
    }
    posMetaRef.current = null
  }, [])

  useEffect(() => {
    let alive = true
    setErr('')
    async function load() {
      if (!rowsRef.current.length) setStatus('loading')
      try {
        const limit = range === '60' ? 300 : range === '15' ? 300 : 400
        const data = await labTradeApi.candles(symbol, range, limit)
        if (!alive) return
        const candles = (data.candles || []).map(toChartCandle).filter((c) => Number.isFinite(c.time))
        if (candles.length) {
          setRows(candles)
          displayRowsRef.current = candles
        }
        setErr(data.stale ? 'Cached chart (live feed busy)' : '')
        setStatus('ready')
      } catch (e) {
        if (alive) {
          if (!rowsRef.current.length) {
            setErr(e.message || String(e))
            setStatus('error')
          } else {
            setErr('Using cached chart — refresh soon')
            setStatus('ready')
          }
        }
      }
    }
    load()
    const id = setInterval(load, range === '5' ? 60000 : 120000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol, range])

  useEffect(() => {
    if (!hostRef.current) return undefined
    const pf = priceFormat(symbol)
    const chart = createChart(hostRef.current, {
      layout: { background: { color: 'transparent' }, textColor: '#c5b8e8' },
      grid: {
        vertLines: { color: 'rgba(167, 139, 250, 0.08)' },
        horzLines: { color: 'rgba(167, 139, 250, 0.08)' },
      },
      rightPriceScale: { borderColor: 'rgba(167, 139, 250, 0.2)' },
      timeScale: { borderColor: 'rgba(167, 139, 250, 0.2)', timeVisible: true },
    })
    const series = chart.addCandlestickSeries({
      upColor: '#6ee7b7',
      downColor: '#f87171',
      borderUpColor: '#6ee7b7',
      borderDownColor: '#f87171',
      wickUpColor: '#6ee7b7',
      wickDownColor: '#f87171',
      priceLineVisible: true,
      lastValueVisible: true,
      priceFormat: pf,
    })
    const ema20 = chart.addLineSeries({
      color: '#a78bfa',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: pf,
    })
    const ema50 = chart.addLineSeries({
      color: '#fbbf24',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: pf,
    })
    chartRef.current = chart
    seriesRef.current = series
    ema20Ref.current = ema20
    ema50Ref.current = ema50
    liveLineRef.current = null
    stopLinesRef.current = { entry: null, sl: null, tp: null }

    const ro = new ResizeObserver(() => {
      if (hostRef.current) chart.applyOptions({ width: hostRef.current.clientWidth, height: hostRef.current.clientHeight })
    })
    ro.observe(hostRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      liveLineRef.current = null
      stopLinesRef.current = { entry: null, sl: null, tp: null }
    }
  }, [symbol])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    const ema20 = ema20Ref.current
    const ema50 = ema50Ref.current
    if (!chart || !series || !rows.length) return

    displayRowsRef.current = [...rows]
    series.setData(rows)
    const closes = rows.map((r) => r.close)
    const e20 = emaSeries(closes, 20)
    const e50 = emaSeries(closes, 50)
    ema20.setData(rows.map((r, i) => (e20[i] != null ? { time: r.time, value: e20[i] } : null)).filter(Boolean))
    ema50.setData(rows.map((r, i) => (e50[i] != null ? { time: r.time, value: e50[i] } : null)).filter(Boolean))
    chart.timeScale().scrollToRealTime()
  }, [rows])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const px = Number(livePrice)
    if (!Number.isFinite(px) || px <= 0) return

    setLiveAt(Date.now())
    const title = `LIVE ${fmtLive(symbol, px)}`
    if (!liveLineRef.current) {
      liveLineRef.current = series.createPriceLine({
        price: px,
        color: '#ffffff',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title,
      })
    } else {
      try {
        liveLineRef.current.applyOptions({ price: px, title })
      } catch {
        liveLineRef.current = series.createPriceLine({
          price: px,
          color: '#ffffff',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title,
        })
      }
    }

    const hist = displayRowsRef.current
    if (!hist.length) return
    const last = hist[hist.length - 1]
    const updated = {
      time: last.time,
      open: last.open,
      high: Math.max(Number(last.high), px),
      low: Math.min(Number(last.low), px),
      close: px,
    }
    try {
      series.update(updated)
      displayRowsRef.current = [...hist.slice(0, -1), updated]
    } catch {
      /* mid-reset */
    }
  }, [livePrice, symbol])

  useEffect(() => {
    if (dragRef.current.kind) return
    if (!activePos) {
      clearStopLines()
      return
    }
    syncStopLines(activePos)
  }, [activePos, clearStopLines, syncStopLines])

  const nearestDragKind = useCallback((clientY) => {
    const series = seriesRef.current
    const meta = posMetaRef.current
    if (!series || !meta || !editable) return null
    const rect = hostRef.current?.getBoundingClientRect()
    if (!rect) return null

    const candidates = []
    if (meta.stop_loss != null) {
      const y = series.priceToCoordinate(meta.stop_loss)
      if (y != null) candidates.push({ kind: 'sl', dist: Math.abs(clientY - rect.top - y) })
    }
    if (meta.take_profit != null) {
      const y = series.priceToCoordinate(meta.take_profit)
      if (y != null) candidates.push({ kind: 'tp', dist: Math.abs(clientY - rect.top - y) })
    }
    candidates.sort((a, b) => a.dist - b.dist)
    if (!candidates.length || candidates[0].dist > DRAG_HIT_PX) return null
    return candidates[0].kind
  }, [editable])

  const applyDragPrice = useCallback(
    (kind, price) => {
      const meta = posMetaRef.current
      const lines = stopLinesRef.current
      if (!meta || !lines[kind]) return null
      const rounded = roundPrice(symbol, price)
      if (!validStopPrice(meta.side, meta.entry_price, rounded, kind)) return null
      const title =
        kind === 'sl' ? `SL ${fmtLive(symbol, rounded)}` : `TP ${fmtLive(symbol, rounded)}`
      lines[kind].applyOptions({ price: rounded, title })
      return rounded
    },
    [symbol],
  )

  useEffect(() => {
    if (!editable) return undefined
    const wrap = wrapRef.current
    if (!wrap) return undefined

    const setChartLocked = (locked) => {
      chartRef.current?.applyOptions({
        handleScroll: !locked,
        handleScale: !locked,
      })
    }

    const onMove = (ev) => {
      const drag = dragRef.current
      if (!drag.kind) return
      const series = seriesRef.current
      const rect = hostRef.current?.getBoundingClientRect()
      if (!series || !rect) return
      const price = series.coordinateToPrice(ev.clientY - rect.top)
      if (price == null) return
      const applied = applyDragPrice(drag.kind, price)
      if (applied != null) {
        const meta = posMetaRef.current
        const pipN =
          meta != null ? pipsFromEntryPrice(symbol, meta.side, meta.entry_price, applied, drag.kind) : null
        setDragHint(
          `${drag.kind === 'sl' ? 'SL' : 'TP'} → ${fmtLive(symbol, applied)}${pipN != null ? ` · ${pipN} pips` : ''}`,
        )
      }
    }

    const onUp = async (ev) => {
      const drag = dragRef.current
      if (!drag.kind) return
      dragRef.current = { kind: null, startPrice: null }
      setChartLocked(false)
      wrap.style.cursor = ''
      document.body.style.userSelect = ''

      const meta = posMetaRef.current
      const series = seriesRef.current
      const rect = hostRef.current?.getBoundingClientRect()
      if (!meta || !series || !rect || !onUpdateStops) {
        setDragHint('')
        return
      }

      const price = series.coordinateToPrice(ev.clientY - rect.top)
      const rounded = price != null ? roundPrice(symbol, price) : null
      setDragHint('')

      if (rounded == null || !validStopPrice(meta.side, meta.entry_price, rounded, drag.kind)) {
        syncStopLines(activePos)
        return
      }

      const orig = drag.kind === 'sl' ? meta.stop_loss : meta.take_profit
      if (orig != null && Math.abs(orig - rounded) < (symbol === 'XAUUSD' ? 0.001 : 0.000001)) {
        return
      }

      const body = drag.kind === 'sl' ? { stop_loss: rounded } : { take_profit: rounded }
      try {
        await onUpdateStops(meta.id, body)
      } catch {
        syncStopLines(activePos)
      }
    }

    const onDown = (ev) => {
      if (ev.button !== 0) return
      const kind = nearestDragKind(ev.clientY)
      if (!kind) return
      ev.preventDefault()
      const meta = posMetaRef.current
      dragRef.current = {
        kind,
        startPrice: kind === 'sl' ? meta?.stop_loss : meta?.take_profit,
      }
      setChartLocked(true)
      wrap.style.cursor = 'ns-resize'
      document.body.style.userSelect = 'none'
      setDragHint(`Drag ${kind === 'sl' ? 'SL' : 'TP'} — release to save`)
    }

    wrap.addEventListener('mousedown', onDown)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      wrap.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      setChartLocked(false)
    }
  }, [activePos, applyDragPrice, editable, nearestDragKind, onUpdateStops, syncStopLines, symbol])

  return (
    <div className="lab-chart-wrap">
      <div className="lab-chart-head">
        <span className="lab-muted">
          {symbol} candles
          {liveAt ? <span className="lab-live-dot"> · live</span> : null}
          {editable ? <span className="lab-chart-drag-hint"> · drag SL/TP lines</span> : null}
        </span>
        <div className="lab-chart-ranges">
          {RANGES.map((r) => (
            <button key={r.id} type="button" className={range === r.id ? 'on' : ''} onClick={() => setRange(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {err ? <p className="lab-error-inline lab-chart-note">{err}</p> : null}
      {dragHint ? <p className="lab-chart-drag-status">{dragHint}</p> : null}
      <div ref={wrapRef} className={`lab-chart-host-wrap${editable ? ' lab-chart-editable' : ''}`}>
        <div ref={hostRef} className="lab-chart-host" />
      </div>
      <p className="lab-chart-legend lab-muted">
        {status === 'loading' ? 'Loading…' : `EMA 20 · EMA 50 · ${rows.length} bars · real-time tick`}
        {activePos ? ` · Entry / SL / TP on chart` : ''}
      </p>
    </div>
  )
}
