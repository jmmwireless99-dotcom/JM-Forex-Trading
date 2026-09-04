import { useEffect } from 'react'
import TradePage from './pages/TradePage.jsx'
import { PAIR_URL_SYMBOLS, pairTradePath } from './routing.js'
import { setLabSessionPair } from './api.js'

export default function PairTradeApp({ pair }) {
  useEffect(() => {
    setLabSessionPair(pair)
    document.title = `${pair} · JM Lab paper`
    return () => setLabSessionPair(null)
  }, [pair])

  return (
    <div className="lab-app lab-pair-app">
      <header className="lab-nav lab-pair-nav">
        <div className="lab-nav-inner">
          <a href="/lab/#suite" className="lab-brand">
            JM <span>Lab</span>
          </a>
          <span className="lab-pair-nav-title">{pair} · paper scalper</span>
          <nav className="lab-pair-nav-links" aria-label="4-pair lab">
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
        </div>
      </header>
      <main className="lab-main">
        <TradePage fixedPair={pair} />
      </main>
      <footer className="lab-footer">
        {pair} paper trading · lab backend only ·{' '}
        <a href="/lab/#suite">4-pair dashboard</a>
      </footer>
    </div>
  )
}
