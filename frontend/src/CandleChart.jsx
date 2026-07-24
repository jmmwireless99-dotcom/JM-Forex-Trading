import { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'

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

export default function CandleChart({ candles = [], liveCandle = null, symbol = 'XAUUSD' }) {
  const hostRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

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
        secondsVisible: true,
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
    if (!seriesRef.current) return
    const rows = candles.map(toChartCandle)
    // Dedupe by time ascending
    const map = new Map()
    for (const row of rows) map.set(row.time, row)
    if (liveCandle) {
      const live = toChartCandle(liveCandle)
      map.set(live.time, live)
    }
    const data = Array.from(map.values()).sort((a, b) => a.time - b.time)
    if (data.length) {
      seriesRef.current.setData(data)
      chartRef.current?.timeScale().scrollToRealTime()
    }
  }, [candles, liveCandle])

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <h2>{symbol} · live candles</h2>
        <span className="meta">OHLC stream</span>
      </div>
      <div className="chart-canvas" ref={hostRef} />
    </div>
  )
}
