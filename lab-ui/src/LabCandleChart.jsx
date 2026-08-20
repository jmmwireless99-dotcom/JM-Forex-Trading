import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { labTradeApi } from './api.js'

const RANGES = [
  { id: '5', label: 'M5' },
  { id: '15', label: 'M15' },
  { id: '60', label: 'H1' },
]

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

export default function LabCandleChart({ symbol = 'EURUSD', livePrice = null, positions = [] }) {
  const hostRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const ema20Ref = useRef(null)
  const ema50Ref = useRef(null)
  const priceLinesRef = useRef([])
  const liveLineRef = useRef(null)
  const displayRowsRef = useRef([])

  const [range, setRange] = useState('5')
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('idle')
  const [err, setErr] = useState('')
  const [liveAt, setLiveAt] = useState(null)
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  const openPos = useMemo(
    () => (positions || []).filter((p) => (p.status || 'OPEN').toUpperCase() === 'OPEN'),
    [positions],
  )

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
    }
  }, [symbol])

  // Historical candles + EMAs
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

  // Live forming bar + LIVE price line (updates every tick)
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

  // Entry / SL / TP lines
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return

    for (const pl of priceLinesRef.current) {
      try {
        series.removePriceLine(pl)
      } catch {
        /* ignore */
      }
    }
    priceLinesRef.current = []
    for (const p of openPos) {
      if (p.symbol !== symbol) continue
      priceLinesRef.current.push(
        series.createPriceLine({
          price: Number(p.entry_price),
          color: p.side === 'BUY' ? '#6ee7b7' : '#f87171',
          lineWidth: 1,
          lineStyle: 2,
          title: `${p.side} entry`,
        }),
      )
      if (p.stop_loss != null) {
        priceLinesRef.current.push(
          series.createPriceLine({ price: Number(p.stop_loss), color: '#f87171', lineWidth: 1, title: 'SL' }),
        )
      }
      if (p.take_profit != null) {
        priceLinesRef.current.push(
          series.createPriceLine({ price: Number(p.take_profit), color: '#6ee7b7', lineWidth: 1, title: 'TP' }),
        )
      }
    }
  }, [openPos, symbol])

  return (
    <div className="lab-chart-wrap">
      <div className="lab-chart-head">
        <span className="lab-muted">
          {symbol} candles
          {liveAt ? <span className="lab-live-dot"> · live</span> : null}
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
      <div ref={hostRef} className="lab-chart-host" />
      <p className="lab-chart-legend lab-muted">
        {status === 'loading' ? 'Loading…' : `EMA 20 · EMA 50 · ${rows.length} bars · real-time tick`}
      </p>
    </div>
  )
}
