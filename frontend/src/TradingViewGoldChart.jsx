import { useEffect, useId, useRef, useState } from 'react'

const TV_SCRIPT = 'https://s3.tradingview.com/tv.js'

function loadTvScript() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if (window.TradingView?.widget) return Promise.resolve()
  if (window.__jmTvScriptPromise) return window.__jmTvScriptPromise

  window.__jmTvScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${TV_SCRIPT}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('TradingView script failed')))
      // already loaded
      if (window.TradingView?.widget) resolve()
      return
    }
    const script = document.createElement('script')
    script.src = TV_SCRIPT
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('TradingView script failed'))
    document.head.appendChild(script)
  })
  return window.__jmTvScriptPromise
}

/**
 * Live gold chart via TradingView Advanced Chart (tv.js).
 * Uses fixed pixel height so the canvas is never 0×0 under flex layouts.
 */
/** Private saved layout — opens only when YOU are logged into TradingView. */
const USER_CHART_URL = 'https://www.tradingview.com/chart/Bhih3eRv/'

export default function TradingViewGoldChart({
  symbol = 'TVC:GOLD',
  interval = '5',
}) {
  const reactId = useId().replace(/:/g, '')
  const containerId = `tv_xau_${reactId}`
  const hostRef = useRef(null)
  const widgetRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [activeSymbol, setActiveSymbol] = useState(symbol)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    setActiveSymbol(symbol)
  }, [symbol])

  useEffect(() => {
    let cancelled = false
    const host = hostRef.current
    if (!host) return undefined

    setStatus('loading')
    host.innerHTML = ''
    const mount = document.createElement('div')
    mount.id = containerId
    mount.style.width = '100%'
    mount.style.height = '100%'
    host.appendChild(mount)

    ;(async () => {
      try {
        await loadTvScript()
        if (cancelled || !window.TradingView?.widget) {
          throw new Error('TradingView API unavailable')
        }
        // Destroy previous instance if any
        try {
          widgetRef.current?.remove?.()
        } catch {
          /* ignore */
        }
        widgetRef.current = new window.TradingView.widget({
          autosize: true,
          width: '100%',
          height: '100%',
          symbol: activeSymbol,
          interval: String(interval),
          timezone: 'Asia/Manila',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#0b1014',
          enable_publishing: false,
          hide_top_toolbar: false,
          hide_legend: false,
          save_image: false,
          allow_symbol_change: true,
          container_id: containerId,
          studies: [
            'MASimple@tv-basicstudies',
            'MAExp@tv-basicstudies',
            'RSI@tv-basicstudies',
          ],
        })
        if (!cancelled) setStatus('ready')
      } catch (err) {
        if (!cancelled) setStatus('error')
        console.error('TradingView chart:', err)
      }
    })()

    return () => {
      cancelled = true
      try {
        widgetRef.current?.remove?.()
      } catch {
        /* ignore */
      }
      widgetRef.current = null
      if (host) host.innerHTML = ''
    }
  }, [activeSymbol, interval, containerId, reloadKey])

  return (
    <div className="chart-wrap tv-chart-wrap">
      <div className="chart-head">
        <h2>XAUUSD · TradingView</h2>
        <span className="meta">Live market · M{interval}</span>
      </div>
      <div className="tv-symbol-bar">
        <button
          type="button"
          className={activeSymbol === 'TVC:GOLD' ? 'on' : ''}
          onClick={() => setActiveSymbol('TVC:GOLD')}
        >
          TVC:GOLD
        </button>
        <button
          type="button"
          className={activeSymbol === 'OANDA:XAUUSD' ? 'on' : ''}
          onClick={() => setActiveSymbol('OANDA:XAUUSD')}
        >
          OANDA:XAUUSD
        </button>
        <button
          type="button"
          className={activeSymbol === 'FOREXCOM:XAUUSD' ? 'on' : ''}
          onClick={() => setActiveSymbol('FOREXCOM:XAUUSD')}
        >
          FOREXCOM
        </button>
        <a
          className="tv-open-link"
          href={USER_CHART_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="Opens your saved TradingView layout (login required)"
        >
          My chart (Bhih3eRv) ↗
        </a>
        <a
          className="tv-open-link"
          href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(activeSymbol)}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Symbol chart ↗
        </a>
      </div>
      <div className="tv-chart-canvas">
        {status === 'loading' ? (
          <div className="tv-chart-status">Loading TradingView…</div>
        ) : null}
        {status === 'error' ? (
          <div className="tv-chart-status tv-chart-error">
            <p>Hindi mag-load ang chart (adblock / network / TradingView block).</p>
            <div className="tv-chart-actions">
              <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
                Reload chart
              </button>
              <a
                href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(activeSymbol)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open on TradingView
              </a>
            </div>
          </div>
        ) : null}
        <div ref={hostRef} className="tv-chart-host" />
      </div>
    </div>
  )
}
