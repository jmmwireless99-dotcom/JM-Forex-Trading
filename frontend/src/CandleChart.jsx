import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import { api } from './api'

const RANGE_OPTS = [
  { id: 'm5', label: 'M5', hint: 'Desk signal · ~1 month' },
  { id: 'm1tape', label: 'M1', hint: 'Engine M1 · ~4h' },
  { id: 'm15', label: 'M15', hint: '15m · ~5 days' },
  { id: 'h1', label: 'H1', hint: '1h · ~1 month' },
  { id: '1m', label: '1M Daily', hint: '1 day / bar' },
]

const RANGE_ALIASES = {
  live: 'm5',
  '1w': 'h1',
  '1m_h1': 'h1',
  '60': 'h1',
  '5': 'm5',
  '15': 'm15',
}

/** Max bars sent to lightweight-charts (full month retained for scroll). */
const MAX_CHART_BARS = 8640
/** Default visible window on desk M5 (~2 trading days). */
const M5_VISIBLE_BARS = 576

function loadRange() {
  try {
    const saved = localStorage.getItem('jm_desk_chart_range')
    const mapped = RANGE_ALIASES[saved] || saved
    if (RANGE_OPTS.some((r) => r.id === mapped)) return mapped
  } catch {
    /* ignore */
  }
  return 'm5'
}

function toChartCandle(c) {
  const t = Math.floor(new Date(c.open_time || c.timestamp || c.time * 1000).getTime() / 1000)
  return {
    time: t,
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
  }
}

function mergeCandleRows(...groups) {
  const map = new Map()
  for (const group of groups) {
    for (const c of group) {
      const row = typeof c.time === 'number' && Number.isFinite(c.open) ? c : toChartCandle(c)
      if (Number.isFinite(row.time)) map.set(row.time, row)
    }
  }
  return Array.from(map.values()).sort((a, b) => a.time - b.time)
}

/** Reject mixing engine/paper prices with market OHLC (prevents fake crash candles). */
function priceNear(a, b, pct = 0.04) {
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= 0) return false
  return Math.abs(a - b) / b <= pct
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

function utcDayKey(unixSec) {
  return new Date(unixSec * 1000).toISOString().slice(0, 10)
}

function formatDayLabel(unixSec) {
  return new Date(unixSec * 1000).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    timeZone: 'UTC',
  })
}

/** First bar of each UTC day → square marker (daily separators). */
function dayBoundaryMarkers(rows, { maxLabels = 14 } = {}) {
  const out = []
  let prev = null
  for (const r of rows) {
    const key = utcDayKey(r.time)
    if (key === prev) continue
    prev = key
    out.push({
      time: r.time,
      position: 'aboveBar',
      color: 'rgba(240, 199, 94, 0.9)',
      shape: 'square',
      text: '', // label only on recent days — long text stacks vertically
    })
  }
  // Label only the most recent N day boundaries to avoid chart clutter
  for (const m of out.slice(-maxLabels)) {
    m.text = formatDayLabel(m.time)
  }
  return out
}

function sliceLastDays(rows, days) {
  if (!rows.length) return rows
  const cutoff = rows[rows.length - 1].time - days * 86400
  return rows.filter((r) => r.time >= cutoff)
}

function sliceLastBars(rows, maxBars) {
  if (!rows.length || rows.length <= maxBars) return rows
  return rows.slice(-maxBars)
}

function rangeFetchSpec(range) {
  if (range === 'm5') return { kind: 'desk_m5', days: 31 }
  if (range === 'm15') return { interval: '15', limit: 1000, days: 5, dayMarks: true }
  if (range === 'h1') return { interval: '60', limit: 800, days: 31, dayMarks: true }
  if (range === '1m') return { interval: '1d', limit: 45, days: 31, dayMarks: true }
  return null
}

function resolveLivePrice(livePrice, liveCandle, candles) {
  const direct = Number(livePrice)
  if (Number.isFinite(direct) && direct > 0) return direct
  if (liveCandle != null) {
    const c = Number(liveCandle.close ?? liveCandle.mid)
    if (Number.isFinite(c) && c > 0) return c
  }
  if (candles?.length) {
    const last = candles[candles.length - 1]
    const c = Number(last?.close)
    if (Number.isFinite(c) && c > 0) return c
  }
  return null
}

export default function CandleChart({
  candles = [],
  liveCandle = null,
  signalCandles = [],
  liveSignalCandle = null,
  livePrice = null,
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
  const livePriceLineRef = useRef(null)
  const candleTimesRef = useRef([])
  const displayRowsRef = useRef([])
  const fitOnceRef = useRef(false)
  const m5ZoomKeyRef = useRef('')

  const [range, setRange] = useState(loadRange)
  const [histRows, setHistRows] = useState([])
  const [histStatus, setHistStatus] = useState('idle') // idle | loading | ready | error
  const [histError, setHistError] = useState('')

  const openPositions = useMemo(
    () =>
      (positions || []).filter((p) => {
        const st = (p.status?.value || p.status || 'OPEN').toString().toUpperCase()
        return st === 'OPEN'
      }),
    [positions],
  )

  const m1Rows = useMemo(() => buildCandleRows(candles, liveCandle), [candles, liveCandle])

  // M5 uses market gold OHLC only — engine signal candles can sit on a different
  // paper mid (e.g. 4436 vs PAXG 2471) and must NOT be merged into the chart.
  const displayRows = useMemo(() => {
    if (range === 'm1tape') return sliceLastBars(m1Rows, MAX_CHART_BARS)
    return sliceLastBars(histRows, MAX_CHART_BARS)
  }, [range, m1Rows, histRows])

  useEffect(() => {
    fitOnceRef.current = false
    m5ZoomKeyRef.current = ''
  }, [range])

  useEffect(() => {
    if (!hostRef.current) return undefined
    const chart = createChart(hostRef.current, {
      autoSize: true,
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
        scaleMargins: { top: 0.08, bottom: 0.22 },
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
      priceLineVisible: true,
      lastValueVisible: true,
      priceLineColor: 'rgba(255, 255, 255, 0.85)',
      priceLineWidth: 1,
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
      scaleMargins: { top: 0.82, bottom: 0.04 },
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

    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      emaRefs.current = { ema20: null, ema50: null, ema200: null }
      rsiRef.current = null
      rsiLevelLinesRef.current = []
      priceLinesRef.current = []
      livePriceLineRef.current = null
    }
  }, [])

  // Fetch history: desk M5 merges market gold + engine signal tail
  useEffect(() => {
    const spec = rangeFetchSpec(range)
    if (range === 'm1tape') {
      setHistStatus('idle')
      setHistError('')
      setHistRows([])
      return undefined
    }
    if (!spec) {
      setHistStatus('idle')
      setHistError('')
      return undefined
    }
    let alive = true
    setHistStatus('loading')
    setHistError('')
    ;(async () => {
      try {
        if (spec.kind === 'desk_m5') {
          const market = await api.goldCandles({ interval: '5', limit: 9000, days: spec.days })
          if (!alive) return
          let marketRows = (market.candles || [])
            .map((c) => ({
              time: Number(c.time),
              open: Number(c.open),
              high: Number(c.high),
              low: Number(c.low),
              close: Number(c.close),
            }))
            .filter((r) => Number.isFinite(r.time) && Number.isFinite(r.close) && r.close > 500)
          marketRows = sliceLastDays(marketRows, spec.days)
          if (!marketRows.length) throw new Error('No M5 market candles returned')
          setHistRows(marketRows)
          setHistStatus('ready')
          return
        }
        const data = await api.goldCandles({
          interval: spec.interval,
          limit: spec.limit,
          days: spec.days,
        })
        if (!alive) return
        let rows = (data.candles || [])
          .map((c) => ({
            time: Number(c.time),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
          }))
          .filter((r) => Number.isFinite(r.time) && Number.isFinite(r.close))
          .sort((a, b) => a.time - b.time)
        rows = sliceLastDays(rows, spec.days)
        if (!rows.length) throw new Error('No history candles returned')
        setHistRows(rows)
        setHistStatus('ready')
      } catch (e) {
        if (!alive) return
        setHistRows([])
        setHistStatus('error')
        setHistError(e?.message || String(e))
      }
    })()
    return () => {
      alive = false
    }
  }, [range, symbol])

  // Candles + EMA + RSI
  useEffect(() => {
    if (!seriesRef.current) return
    const data = displayRows
    displayRowsRef.current = data
    candleTimesRef.current = data.map((d) => d.time)
    if (!data.length) {
      if (range !== 'm1tape' && histStatus === 'loading') return
      seriesRef.current.setData([])
      emaRefs.current.ema20?.setData([])
      emaRefs.current.ema50?.setData([])
      emaRefs.current.ema200?.setData([])
      rsiRef.current?.setData([])
      return
    }
    seriesRef.current.setData(data)
    const ts = chartRef.current?.timeScale()
    if (ts && range === 'm1tape') {
      ts.scrollToRealTime()
    } else if (ts && range !== 'm5' && !fitOnceRef.current) {
      ts.fitContent()
      fitOnceRef.current = true
    }

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
  }, [displayRows, showEma, showRsi, rsiPeriod, range, histStatus])

  // M5: zoom to recent window once history is loaded (not on every live tick)
  useEffect(() => {
    if (range !== 'm5' || !chartRef.current || !displayRows.length) return
    if (histStatus === 'loading') return
    const key = `${range}|${histStatus}|${histRows.length}`
    if (m5ZoomKeyRef.current === key) return
    m5ZoomKeyRef.current = key
    const ts = chartRef.current.timeScale()
    const from = Math.max(0, displayRows.length - M5_VISIBLE_BARS)
    ts.setVisibleLogicalRange({ from, to: displayRows.length + 2 })
  }, [range, histStatus, histRows.length, displayRows.length])

  // LIVE price line; update forming M5 bar only on desk tabs (not Yahoo-only TF)
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const px = resolveLivePrice(livePrice, liveCandle, candles)
    if (px == null) return

    const rows = displayRowsRef.current
    const last = rows.length ? rows[rows.length - 1] : null
    const pxOk = last ? priceNear(px, last.close, 0.04) : true

    const title = pxOk ? `LIVE ${px.toFixed(2)}` : `DESK ${px.toFixed(2)}`
    if (!livePriceLineRef.current) {
      livePriceLineRef.current = series.createPriceLine({
        price: px,
        color: pxOk ? '#ffffff' : 'rgba(255, 180, 100, 0.85)',
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title,
      })
    } else {
      try {
        livePriceLineRef.current.applyOptions({
          price: px,
          title,
          color: pxOk ? '#ffffff' : 'rgba(255, 180, 100, 0.85)',
        })
      } catch {
        livePriceLineRef.current = series.createPriceLine({
          price: px,
          color: pxOk ? '#ffffff' : 'rgba(255, 180, 100, 0.85)',
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title,
        })
      }
    }

    const canUpdateForming = (range === 'm5' || range === 'm1tape') && pxOk
    if (!canUpdateForming || !last) return

    const updated = {
      time: last.time,
      open: last.open,
      high: Math.max(Number(last.high), px),
      low: Math.min(Number(last.low), px),
      close: px,
    }
    try {
      series.update(updated)
      displayRowsRef.current = [...rows.slice(0, -1), updated]
    } catch {
      /* series may be mid-reset */
    }
  }, [livePrice, liveCandle, candles, range])

  // Entry / SL / TP
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    for (const line of priceLinesRef.current) {
      try {
        series.removePriceLine(line)
      } catch {
        /* ignore */
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

  // Day separators + signal arrows
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    const times = candleTimesRef.current
    const rows = displayRowsRef.current
    if (!times.length) {
      series.setMarkers([])
      return
    }

    const spec = rangeFetchSpec(range)
    const wantDayMarks =
      range === 'm5' || range === 'm1tape' ? rows.length > 0 : Boolean(spec?.dayMarks)
    const dayMarks = wantDayMarks ? dayBoundaryMarkers(rows) : []
    const dayByTime = new Map(dayMarks.map((m) => [m.time, m]))

    const signalMarks = []
    const seen = new Set()
    for (const s of (signals || []).slice(0, 40)) {
      const side = sideOf(s.side)
      if (side !== 'BUY' && side !== 'SELL') continue
      const time = snapToCandleTime(s.timestamp || s.ts || s.created_at, times)
      if (time == null) continue
      const tag = strategyTag(s.strategy)
      const key = `${time}|${side}|${tag}`
      if (seen.has(key)) continue
      seen.add(key)
      const day = dayByTime.get(time)
      const dayTxt = day ? ` · ${day.text}` : ''
      signalMarks.push({
        time,
        position: side === 'BUY' ? 'belowBar' : 'aboveBar',
        color: side === 'BUY' ? '#7dffb3' : '#ff6b6b',
        shape: side === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: `${side === 'BUY' ? '▲' : '▼'} ${tag}${dayTxt}`,
      })
      if (day) dayByTime.delete(time)
    }

    const markers = [...dayByTime.values(), ...signalMarks].sort((a, b) => a.time - b.time)
    series.setMarkers(markers)
  }, [signals, displayRows, range])

  const posCount = openPositions.length
  const sigCount = (signals || []).length
  const lastRsi = useMemo(() => {
    if (!showRsi || displayRows.length < rsiPeriod + 1) return null
    const vals = rsiSeries(
      displayRows.map((d) => d.close),
      rsiPeriod,
    )
    for (let i = vals.length - 1; i >= 0; i -= 1) {
      if (vals[i] != null) return Number(vals[i].toFixed(1))
    }
    return null
  }, [displayRows, showRsi, rsiPeriod])

  const activeRange = RANGE_OPTS.find((r) => r.id === range) || RANGE_OPTS[0]
  const dayCount = useMemo(() => {
    const keys = new Set(displayRows.map((r) => utcDayKey(r.time)))
    return keys.size
  }, [displayRows])
  const livePx = resolveLivePrice(livePrice, liveCandle, candles)

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <h2>{symbol} · desk tape</h2>
        <span className="meta">
          {livePx != null ? `LIVE ${livePx.toFixed(2)} · ` : ''}
          {range === 'm5' ? 'M5 signal · ' : range === 'm1tape' ? 'M1 engine · ' : ''}
          {posCount ? `${posCount} open` : 'flat'} · {sigCount} signals
          {lastRsi != null ? ` · RSI ${lastRsi}` : ''}
          {displayRows.length ? ` · ${displayRows.length} bars` : ''}
          {dayCount ? ` · ${dayCount}d` : ''}
        </span>
      </div>

      <div className="desk-range-bar" role="tablist" aria-label="Desk chart range">
        {RANGE_OPTS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={range === opt.id}
            className={range === opt.id ? 'on' : ''}
            onClick={() => {
              setRange(opt.id)
              try {
                localStorage.setItem('jm_desk_chart_range', opt.id)
              } catch {
                /* ignore */
              }
            }}
          >
            {opt.label}
          </button>
        ))}
        <span className="meta desk-range-hint">{activeRange.hint}</span>
        {histStatus === 'loading' ? <span className="meta">Loading history…</span> : null}
        {histStatus === 'error' ? (
          <span className="meta desk-range-error">{histError || 'History failed'}</span>
        ) : null}
      </div>

      <div className="chart-legend" aria-label="Chart legend">
        <span className="chart-leg ema20">EMA20</span>
        <span className="chart-leg ema50">EMA50</span>
        <span className="chart-leg ema200">EMA200</span>
        <span className="chart-leg rsi">RSI{rsiPeriod}</span>
        <span className="chart-leg live">LIVE</span>
        <span className="chart-leg day">Day</span>
        <span className="chart-leg entry">Entry</span>
        <span className="chart-leg sl">SL</span>
        <span className="chart-leg tp">TP</span>
        <span className="chart-leg buy">▲ BUY</span>
        <span className="chart-leg sell">▼ SELL</span>
      </div>
      <div className="desk-chart-shell desk-chart-shell-rsi">
        <div className="desk-chart-host" ref={hostRef} />
      </div>
      {range !== 'm1tape' ? (
        <p className="desk-history-footnote">
          {range === 'm5'
            ? 'M5 market gold OHLC (GC=F / PAXG) · ~1 month · UTC day separators · white '
            : 'History via market gold OHLC (GC=F / PAXG) · UTC day separators · white '}
          <strong>LIVE</strong> line tracks desk tick when within 4% of the last bar.
        </p>
      ) : null}
    </div>
  )
}
