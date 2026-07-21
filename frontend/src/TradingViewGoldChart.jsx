import { useEffect, useRef } from 'react'

/**
 * Live XAUUSD chart via TradingView Advanced Chart widget.
 * Real market candles (not paper simulator).
 */
export default function TradingViewGoldChart({
  symbol = 'OANDA:XAUUSD',
  interval = '5',
}) {
  const containerRef = useRef(null)

  useEffect(() => {
    const host = containerRef.current
    if (!host) return

    host.innerHTML = ''
    const widgetRoot = document.createElement('div')
    widgetRoot.className = 'tradingview-widget-container'
    widgetRoot.style.height = '100%'
    widgetRoot.style.width = '100%'

    const widget = document.createElement('div')
    widget.className = 'tradingview-widget-container__widget'
    widget.style.height = 'calc(100% - 28px)'
    widget.style.width = '100%'

    const copyright = document.createElement('div')
    copyright.className = 'tradingview-widget-copyright'
    copyright.innerHTML =
      '<a href="https://www.tradingview.com/symbols/XAUUSD/" rel="noopener nofollow" target="_blank"><span class="blue-text">XAUUSD</span></a><span class="trademark"> by TradingView</span>'

    const script = document.createElement('script')
    script.src =
      'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: 'Asia/Manila',
      theme: 'dark',
      style: '1',
      locale: 'en',
      backgroundColor: 'rgba(11, 16, 20, 1)',
      gridColor: 'rgba(255, 255, 255, 0.06)',
      hide_top_toolbar: false,
      hide_legend: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      hide_volume: false,
      support_host: 'https://www.tradingview.com',
      studies: [
        'MASimple@tv-basicstudies',
        'MAExp@tv-basicstudies',
        'RSI@tv-basicstudies',
      ],
    })

    widgetRoot.appendChild(widget)
    widgetRoot.appendChild(copyright)
    widgetRoot.appendChild(script)
    host.appendChild(widgetRoot)

    return () => {
      host.innerHTML = ''
    }
  }, [symbol, interval])

  return (
    <div className="chart-wrap tv-chart-wrap">
      <div className="chart-head">
        <h2>XAUUSD · TradingView</h2>
        <span className="meta">Live market · M{interval}</span>
      </div>
      <div className="tv-chart-canvas" ref={containerRef} />
    </div>
  )
}
