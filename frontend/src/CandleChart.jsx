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

/** Wilder RSI series (period 14 — same as EMA_RSI_Scalp). */
function rsiSeries(closes, period = 14) {
  const out = new Array(closes.length).fill(null)
  if (closes.length < period + 1) return out
  let avgGain = 0
  let avgLoss = 0
  for (let i = 1; i <= period; i += 1) {
    const ch = closes[i] - closes[i - 1]
    if (ch >= 0) avgGain += ch
    else avgLoss -= ch
  }
  avgGain /= period
  avgLoss /= period
  const toRsi = (g, l) => {
    if (l <= 1e-12) return 100
    const rs = g / l
    return 100 - 100 / (1 + rs)
  }
  out[period] = toRsi(avgGain, avgLoss)
  for (let i = period + 1; i < closes.length; i += 1) {
    const ch = closes[i] - closes[i - 1]
    const gain = ch > 0 ? ch : 0
    const loss = ch < 0 ? -ch : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    out[i] = toRsi(avgGain, avgLoss)
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
  showRsi = true,
  rsiPeriod = 14,
}) {
  const hostRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const emaRefs = useRef({ ema20: null, ema50: null, ema200: null })
  const rsiRef = useRef(null)
  const rsiLevelLinesRef = useRef([])
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
      rightPriceScale: {
        borderColor: 'rgba(125, 255, 179, 0.15)',
        scaleMargins: { top: 0.05, bottom: 0.28 },
      },
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
    // Bottom pane: RSI(14) on its own price scale
    const rsiSeriesApi = chart.addLineSeries({
      color: '#e8a0ff',
      lineWidth: 2,
      priceScaleId: 'rsi',
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      title: 'RSI',
    })
    chart.priceScale('rsi').applyOptions({
      scaleMargins: { top: 0.78, bottom: 0.02 },
      borderVisible: false,
      drawTicks: false,
    })
    rsiLevelLinesRef.current = [
      rsiSeriesApi.createPriceLine({
        price: 70,
        color: 'rgba(255, 107, 107, 0.55)',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: '70',
      }),
      rsiSeriesApi.createPriceLine({
        price: 50,
        color: 'rgba(197, 212, 207, 0.35)',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: '',
      }),
      rsiSeriesApi.createPriceLine({
        price: 30,
        color: 'rgba(125, 255, 179, 0.55)',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: '30',
      }),
    ]
    rsiRef.current = rsiSeriesApi
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
      rsiRef.current = null
      rsiLevelLinesRef.current = []
      priceLinesRef.current = []
    }
  }, [])

  // Candles + EMA + RSI overlays
  useEffect(() => {
    if (!seriesRef.current) return
    const data = buildCandleRows(candles, liveCandle)
    candleTimesRef.current = data.map((d) => d.time)
    if (!data.length) return
    seriesRef.current.setData(data)
    chartRef.current?.timeScale().scrollToRealTime()

    const closes = data.map((d) => d.close)
    const pack = (values, digits = 3) =>
      data
        .map((d, i) =>
          values[i] == null
            ? null
            : { time: d.time, value: Number(values[i].toFixed(digits)) },
        )
        .filter(Boolean)

    if (!showEma) {
      emaRefs.current.ema20?.setData([])
      emaRefs.current.ema50?.setData([])
      emaRefs.current.ema200?.setData([])
    } else {
      emaRefs.current.ema20?.setData(pack(emaSeries(closes, 20)))
      emaRefs.current.ema50?.setData(pack(emaSeries(closes, 50)))
      emaRefs.current.ema200?.setData(pack(emaSeries(closes, 200)))
    }

    if (!showRsi || !rsiRef.current) {
      rsiRef.current?.setData([])
      return
    }
    rsiRef.current.setData(pack(rsiSeries(closes, rsiPeriod), 2))
  }, [candles, liveCandle, showEma, showRsi, rsiPeriod])

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
  const lastRsi = useMemo(() => {
    const data = buildCandleRows(candles, liveCandle)
    if (!showRsi || data.length < rsiPeriod + 1) return null
    const vals = rsiSeries(
      data.map((d) => d.close),
      rsiPeriod,
    )
    for (let i = vals.length - 1; i >= 0; i -= 1) {
      if (vals[i] != null) return Number(vals[i].toFixed(1))
    }
    return null
  }, [candles, liveCandle, showRsi, rsiPeriod])

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <h2>{symbol} · desk tape</h2>
        <span className="meta">
          {posCount ? `${posCount} open` : 'flat'} · {sigCount} signals
          {lastRsi != null ? ` · RSI ${lastRsi}` : ''}
        </span>
      </div>
      <div className="chart-legend" aria-label="Chart legend">
        <span className="chart-leg ema20">EMA20</span>
        <span className="chart-leg ema50">EMA50</span>
        <span className="chart-leg ema200">EMA200</span>
        <span className="chart-leg rsi">RSI{rsiPeriod}</span>
        <span className="chart-leg entry">Entry</span>
        <span className="chart-leg sl">SL</span>
        <span className="chart-leg tp">TP</span>
        <span className="chart-leg buy">▲ BUY</span>
        <span className="chart-leg sell">▼ SELL</span>
      </div>
      <div className="chart-canvas chart-canvas-rsi" ref={hostRef} />
    </div>
  )
}
