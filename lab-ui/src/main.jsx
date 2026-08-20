import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import PairTradeApp from './PairTradeApp.jsx'
import { parsePairFromPath } from './routing.js'
import './Lab.css'

function Root() {
  const pair = parsePairFromPath()
  if (pair) return <PairTradeApp pair={pair} />
  return <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
