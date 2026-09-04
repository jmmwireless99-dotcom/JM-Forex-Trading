import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import PairTradeApp from './PairTradeApp.jsx'
import { parsePairFromPath } from './routing.js'
import './Lab.css'

function Root() {
  const pair = parsePairFromPath()
  if (pair) {
    // Pair URLs are lab-only trade pages — ignore #home etc. from shared /lab/ links
    if (window.location.hash) {
      history.replaceState(null, '', window.location.pathname + window.location.search)
    }
    return <PairTradeApp pair={pair} />
  }
  return <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
