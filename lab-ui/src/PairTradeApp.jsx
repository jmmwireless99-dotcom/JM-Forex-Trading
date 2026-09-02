import { useEffect } from 'react'
import TradePage from './pages/TradePage.jsx'
import { PAIR_URL_SYMBOLS, pairTradePath } from './routing.js'
import { setLabSessionPair } from './api.js'

export default function PairTradeApp({ pair }) {
  useEffect(() => {
    setLabSessionPair(pair)
    document.title = `${pair} · JM Lab demo`
    return () => setLabSessionPair(null)
  }, [pair])

  return (
    <div className="lab-app lab-pair-app">
      <header className="lab-nav lab-pair-nav">
        <div className="lab-nav-inner">
          <a href="/lab/" className="lab-brand">
            JM <span>Lab</span>
          </a>
          <span className="lab-pair-nav-title">{pair} demo</span>
          <nav className="lab-pair-nav-links" aria-label="Other pairs">
            {PAIR_URL_SYMBOLS.map((id) => (
              <a
                key={id}
                href={pairTradePath(id)}
                className={id === pair ? 'on' : ''}
                target={id === pair ? undefined : '_blank'}
                rel={id === pair ? undefined : 'noopener noreferrer'}
              >
                {id}
              </a>
            ))}
          </nav>
          <a href="/fx/" className="lab-desk-link">
            JM FX desk ↗
          </a>
        </div>
      </header>
      <main className="lab-main">
        <TradePage fixedPair={pair} />
      </main>
      <footer className="lab-footer">
        {pair} paper trading · open other pairs in new tabs ·{' '}
          <a href="/lab/#suite">4-pair dashboard</a>
      </footer>
    </div>
  )
}
