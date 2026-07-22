import { useEffect, useId, useRef, useState } from 'react'

/**
 * Live XAUUSD chart via TradingView widgetembed iframe.
 * More stable under React remounts than the script-injection embed.
 */
export default function TradingViewGoldChart({
  symbol = 'OANDA:XAUUSD',
  interval = '5',
}) {
  const reactId = useId().replace(/:/g, '')
  const frameId = `tv_xau_${reactId}`
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [reloadKey, setReloadKey] = useState(0)
  const timerRef = useRef(null)

  const src = new URL('https://www.tradingview.com/widgetembed/')
  src.searchParams.set('frameElementId', frameId)
  src.searchParams.set('symbol', symbol)
  src.searchParams.set('interval', String(interval))
  src.searchParams.set('hidesidetoolbar', '0')
  src.searchParams.set('hidetoptoolbar', '0')
  src.searchParams.set('symboledit', '0')
  src.searchParams.set('saveimage', '0')
  src.searchParams.set('toolbarbg', '0b1014')
  src.searchParams.set('studies', JSON.stringify(['MASimple@tv-basicstudies', 'MAExp@tv-basicstudies', 'RSI@tv-basicstudies']))
  src.searchParams.set('theme', 'dark')
  src.searchParams.set('style', '1')
  src.searchParams.set('timezone', 'Asia/Manila')
  src.searchParams.set('withdateranges', '1')
  src.searchParams.set('hideideas', '1')
  src.searchParams.set('hidevolume', '0')
  src.searchParams.set('locale', 'en')

  useEffect(() => {
    setStatus('loading')
    if (timerRef.current) clearTimeout(timerRef.current)
    // If iframe never fires load (blocked/adblock), surface a recovery UI.
    timerRef.current = setTimeout(() => {
      setStatus((s) => (s === 'ready' ? s : 'error'))
    }, 12000)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [symbol, interval, reloadKey])

  return (
    <div className="chart-wrap tv-chart-wrap">
      <div className="chart-head">
        <h2>XAUUSD · TradingView</h2>
        <span className="meta">Live market · M{interval}</span>
      </div>
      <div className="tv-chart-canvas">
        {status === 'loading' ? (
          <div className="tv-chart-status">Loading TradingView…</div>
        ) : null}
        {status === 'error' ? (
          <div className="tv-chart-status tv-chart-error">
            <p>TradingView chart did not load (blocked network, adblock, or timeout).</p>
            <div className="tv-chart-actions">
              <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
                Reload chart
              </button>
              <a
                href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open on TradingView
              </a>
            </div>
          </div>
        ) : null}
        <iframe
          key={`${frameId}-${reloadKey}`}
          id={frameId}
          title="XAUUSD TradingView"
          src={src.toString()}
          className={`tv-chart-frame${status === 'error' ? ' is-hidden' : ''}`}
          allow="fullscreen"
          onLoad={() => {
            if (timerRef.current) clearTimeout(timerRef.current)
            setStatus('ready')
          }}
          onError={() => setStatus('error')}
        />
      </div>
    </div>
  )
}
