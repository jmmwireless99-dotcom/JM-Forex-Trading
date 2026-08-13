import { useEffect, useMemo, useRef } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'

function toChartCandle(c) {
  const t = Math.floor(new Date(c.open_time || c.timestamp).getTime() / 1000)
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

function strategyTag(name = '') {
  const n = String(name).toUpperCase()
  if (n.includes('VWAP')) return 'VWAP'
  if (n.includes('EMA_RSI') || n.includes('EMA+RSI')) return 'EMA'
  if (n.includes('JUDAS') || n.includes('LONDON')) return 'JUD'
  if (n.includes('SMC') || n.includes('LIQUIDITY')) return 'SMC'
  if (n.includes('AI_ML') || n.startsWith('AI')) return 'AI'
  if (n.includes('EMA')) return 'EMA'
  return (name || 'SIG').slice(0, 4).toUpperCase()
}

function sideOf(value) {
  const s = (value?.value || value || '').toString().toUpperCase()
  return s === 'BUY' ? 'BUY' : s === 'SELL' ? 'SELL' : s
}

function snapToCandleTime(ts, candleTimes) {
  if (!candleTimes.length) return null
  const t = Math.floor(new Date(ts).getTime() / 1000)
  // Prefer same-or-earlier bar so markers attach to an existing candle.
  let best = candleTimes[0]
  for (const ct of candleTimes) {
    if (ct <= t) best = ct
    else break
  }
  return best
}

function buildCandleRows(candles, liveCandle) {
  const map = new Map()
  for (const c of candles) {
    const row = toChartCandle(c)
    if (Number.isFinite(row.time)) map.set(row.time, row)
  }
  if (liveCandle) {
    const live = toChartCandle(liveCandle)
    if (Number.isFinite(live.time)) map.set(live.time, live)
  }
  return Array.from(map.values()).sort((a, b) => a.time - b.time)
}

export default function CandleChart({
  candles = [],
  liveCandle = null,
  symbol = 'XAUUSD',
  positions = [],
  signals = [],
  showEma = true,
}) {
  const hostRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const emaRefs = useRef({ ema20: null, ema50: null, ema200: null })
  const priceLinesRef = useRef([])
  const candleTimesRef = useRef([])

  const openPositions = useMemo(
    () =>
      (positions || []).filter((p) => {
        const st = (p.status?.value || p.status || 'OPEN').toString().toUpperCase()
        return st === 'OPEN'
      }),
    [positions],
  )

  useEffect(() => {
    if (!hostRef.current) return undefined
    const chart = createChart(hostRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#c5d4cf',
      },
      grid: {
        vertLines: { color: 'rgba(125, 255, 179, 0.06)' },
        horzLines: { color: 'rgba(125, 255, 179, 0.06)' },
      },
      rightPriceScale: { borderColor: 'rgba(125, 255, 179, 0.15)' },
      timeScale: {
        borderColor: 'rgba(125, 255, 179, 0.15)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: 'rgba(125, 255, 179, 0.35)' },
        horzLine: { color: 'rgba(125, 255, 179, 0.35)' },
      },
    })
    const series = chart.addCandlestickSeries({
      upColor: '#7dffb3',
      downColor: '#ff6b6b',
      borderUpColor: '#7dffb3',
      borderDownColor: '#ff6b6b',
      wickUpColor: '#7dffb3',
      wickDownColor: '#ff6b6b',
    })
    emaRefs.current.ema20 = chart.addLineSeries({
      color: '#f0c75e',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA20',
    })
    emaRefs.current.ema50 = chart.addLineSeries({
      color: '#6ec8ff',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA50',
    })
    emaRefs.current.ema200 = chart.addLineSeries({
      color: '#c79bff',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA200',
    })
    chartRef.current = chart
    seriesRef.current = series

    const ro = new ResizeObserver(() => {
      if (!hostRef.current) return
      chart.applyOptions({
        width: hostRef.current.clientWidth,
        height: hostRef.current.clientHeight,
      })
    })
    ro.observe(hostRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      emaRefs.current = { ema20: null, ema50: null, ema200: null }
      priceLinesRef.current = []
    }
  }, [])

  // Candles + EMA overlays
  useEffect(() => {
    if (!seriesRef.current) return
    const data = buildCandleRows(candles, liveCandle)
    candleTimesRef.current = data.map((d) => d.time)
    if (!data.length) return
    seriesRef.current.setData(data)
    chartRef.current?.timeScale().scrollToRealTime()

    if (!showEma) {
      emaRefs.current.ema20?.setData([])
      emaRefs.current.ema50?.setData([])
      emaRefs.current.ema200?.setData([])
      return
    }
    const closes = data.map((d) => d.close)
    const pack = (values) =>
      data
        .map((d, i) =>
          values[i] == null
            ? null
            : { time: d.time, value: Number(values[i].toFixed(3)) },
        )
        .filter(Boolean)
    emaRefs.current.ema20?.setData(pack(emaSeries(closes, 20)))
    emaRefs.current.ema50?.setData(pack(emaSeries(closes, 50)))
    emaRefs.current.ema200?.setData(pack(emaSeries(closes, 200)))
  }, [candles, liveCandle, showEma])

  // Open trade Entry / SL / TP price lines
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    for (const line of priceLinesRef.current) {
      try {
        series.removePriceLine(line)
      } catch {
        /* already removed with chart */
      }
    }
    priceLinesRef.current = []

    openPositions.forEach((p, idx) => {
      const side = sideOf(p.side)
      const tag = openPositions.length > 1 ? ` #${idx + 1}` : ''
      const specs = [
        {
          price: Number(p.entry_price ?? p.entry),
          color: side === 'BUY' ? '#7dffb3' : '#ff9f6b',
          title: `ENT${tag}`,
          lineStyle: LineStyle.Solid,
          lineWidth: 2,
        },
        {
          price: Number(p.stop_loss),
          color: '#ff6b6b',
          title: `SL${tag}`,
          lineStyle: LineStyle.Dashed,
          lineWidth: 1,
        },
        {
          price: Number(p.take_profit),
          color: '#7dffb3',
          title: `TP${tag}`,
          lineStyle: LineStyle.Dashed,
          lineWidth: 1,
        },
      ]
      for (const spec of specs) {
        if (!Number.isFinite(spec.price) || spec.price <= 0) continue
        const line = series.createPriceLine({
          price: spec.price,
          color: spec.color,
          lineWidth: spec.lineWidth,
          lineStyle: spec.lineStyle,
          axisLabelVisible: true,
          title: spec.title,
        })
        priceLinesRef.current.push(line)
      }
    })
  }, [openPositions])

  // Signal arrows (BUY ↑ / SELL ↓) with short strategy tags (EMA, SMC, …)
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const times = candleTimesRef.current
    if (!times.length) {
      series.setMarkers([])
      return
    }
    const recent = (signals || []).slice(0, 40)
    const markers = []
    const seen = new Set()
    for (const s of recent) {
      const side = sideOf(s.side)
      if (side !== 'BUY' && side !== 'SELL') continue
      const time = snapToCandleTime(s.timestamp || s.ts || s.created_at, times)
      if (time == null) continue
      const tag = strategyTag(s.strategy)
      const key = `${time}|${side}|${tag}`
      if (seen.has(key)) continue
      seen.add(key)
      markers.push({
        time,
        position: side === 'BUY' ? 'belowBar' : 'aboveBar',
        color: side === 'BUY' ? '#7dffb3' : '#ff6b6b',
        shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `${side === 'BUY' ? '▲' : '▼'} ${tag}`,
      })
    }
    markers.sort((a, b) => a.time - b.time)
    series.setMarkers(markers)
  }, [signals, candles, liveCandle])

  const posCount = openPositions.length
  const sigCount = (signals || []).length

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <h2>{symbol} · desk tape</h2>
        <span className="meta">
          {posCount ? `${posCount} open` : 'flat'} · {sigCount} signals
        </span>
      </div>
      <div className="chart-legend" aria-label="Chart legend">
        <span className="chart-leg ema20">EMA20</span>
        <span className="chart-leg ema50">EMA50</span>
        <span className="chart-leg ema200">EMA200</span>
        <span className="chart-leg entry">Entry</span>
        <span className="chart-leg sl">SL</span>
        <span className="chart-leg tp">TP</span>
        <span className="chart-leg buy">▲ BUY</span>
        <span className="chart-leg sell">▼ SELL</span>
      </div>
      <div className="chart-canvas" ref={hostRef} />
    </div>
  )
}
