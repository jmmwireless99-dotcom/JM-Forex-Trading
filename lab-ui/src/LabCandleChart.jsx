import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
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

  const [range, setRange] = useState('5')
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('idle')
  const [err, setErr] = useState('')
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
        if (candles.length) setRows(candles)
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
    const id = setInterval(load, 120000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol, range])

  useEffect(() => {
    if (!hostRef.current) return undefined
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
    })
    const ema20 = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    const ema50 = chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    chartRef.current = chart
    seriesRef.current = series
    ema20Ref.current = ema20
    ema50Ref.current = ema50

    const ro = new ResizeObserver(() => {
      if (hostRef.current) chart.applyOptions({ width: hostRef.current.clientWidth, height: hostRef.current.clientHeight })
    })
    ro.observe(hostRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    const ema20 = ema20Ref.current
    const ema50 = ema50Ref.current
    if (!chart || !series || !rows.length) return

    let display = [...rows]
    const lp = Number(livePrice)
    if (Number.isFinite(lp) && lp > 0 && display.length) {
      const last = { ...display[display.length - 1] }
      last.close = lp
      last.high = Math.max(last.high, lp)
      last.low = Math.min(last.low, lp)
      display[display.length - 1] = last
    }

    series.setData(display)
    const closes = display.map((r) => r.close)
    const e20 = emaSeries(closes, 20)
    const e50 = emaSeries(closes, 50)
    ema20.setData(display.map((r, i) => (e20[i] != null ? { time: r.time, value: e20[i] } : null)).filter(Boolean))
    ema50.setData(display.map((r, i) => (e50[i] != null ? { time: r.time, value: e50[i] } : null)).filter(Boolean))

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
      const entry = series.createPriceLine({
        price: Number(p.entry_price),
        color: p.side === 'BUY' ? '#6ee7b7' : '#f87171',
        lineWidth: 1,
        lineStyle: 2,
        title: `${p.side} entry`,
      })
      priceLinesRef.current.push(entry)
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

    chart.timeScale().scrollToRealTime()
  }, [rows, livePrice, openPos, symbol])

  return (
    <div className="lab-chart-wrap">
      <div className="lab-chart-head">
        <span className="lab-muted">{symbol} candles</span>
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
        {status === 'loading' ? 'Loading…' : `EMA 20 · EMA 50 · ${rows.length} bars`}
      </p>
    </div>
  )
}
