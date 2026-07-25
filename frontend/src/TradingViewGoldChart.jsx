import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { api } from './api'

/** Private saved layout — opens only when YOU are logged into TradingView. */
const USER_CHART_URL = 'https://www.tradingview.com/chart/Bhih3eRv/'

const MARKET = {
  title: 'XAUUSD · Live gold',
  tvUrl: 'https://www.tradingview.com/symbols/TVC-GOLD/',
  tvLabel: 'TVC:GOLD ↗',
  footnote:
    'Live gold via COMEX futures (GC=F). Strategies still use paper/MT feed — not this chart.',
  loading: 'Loading live gold candles…',
  err: 'Failed to load gold market data',
}

/**
 * Live XAUUSD market chart (Yahoo/COMEX).
 * TradingView embeds are unreliable; this always shows candles.
 */
export default function TradingViewGoldChart({ interval = '5' }) {
  const hostRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const [status, setStatus] = useState('loading')
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState('')
  const [tf, setTf] = useState(String(interval))
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!hostRef.current) return undefined
    const chart = createChart(hostRef.current, {
      layout: {
        background: { color: '#0b1014' },
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
    }
  }, [])

  useEffect(() => {
    let alive = true
    async function load() {
      setStatus('loading')
      try {
        const data = await api.goldCandles({ interval: tf, limit: 400 })
        if (!alive) return
        const rows = (data.candles || []).map((c) => ({
          time: Number(c.time),
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }))
        if (!rows.length) throw new Error('No candles returned')
        seriesRef.current?.setData(rows)
        chartRef.current?.timeScale().scrollToRealTime()
        setMeta(data)
        setStatus('ready')
        setError('')
      } catch (e) {
        if (!alive) return
        setStatus('error')
        setError(e?.message || String(e))
      }
    }
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [tf, reloadKey])

  const price = meta?.price
  const priceLabel =
    price != null
      ? Number(price).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : '—'

  return (
    <div className="chart-wrap tv-chart-wrap">
      <div className="chart-head">
        <h2>{MARKET.title}</h2>
        <span className="meta">
          {meta?.source || meta?.label || 'Market OHLC'} · {priceLabel}
        </span>
      </div>
      <div className="tv-symbol-bar">
        {['1', '5', '15', '60'].map((v) => (
          <button
            key={v}
            type="button"
            className={tf === v ? 'on' : ''}
            onClick={() => setTf(v)}
          >
            {v === '60' ? '1h' : `${v}m`}
          </button>
        ))}
        <a
          className="tv-open-link"
          href={USER_CHART_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          My TradingView ↗
        </a>
        <a
          className="tv-open-link"
          href={MARKET.tvUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          {MARKET.tvLabel}
        </a>
      </div>
      <div className="tv-chart-canvas">
        {status === 'loading' ? (
          <div className="tv-chart-status">{MARKET.loading}</div>
        ) : null}
        {status === 'error' ? (
          <div className="tv-chart-status tv-chart-error">
            <p>{error || MARKET.err}</p>
            <div className="tv-chart-actions">
              <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
                Retry
              </button>
              <a href={MARKET.tvUrl} target="_blank" rel="noopener noreferrer">
                Open TradingView
              </a>
            </div>
          </div>
        ) : null}
        <div ref={hostRef} className="tv-chart-host" />
      </div>
      <p className="tv-chart-footnote">{MARKET.footnote}</p>
    </div>
  )
}
