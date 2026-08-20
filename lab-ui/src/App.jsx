import { useEffect, useState } from 'react'
import Nav from './Nav.jsx'
import HomePage from './pages/HomePage.jsx'
import ComparePage from './pages/ComparePage.jsx'
import SnapshotPage from './pages/SnapshotPage.jsx'
import PairLabPage from './pages/PairLabPage.jsx'
import PairSuitePage from './pages/PairSuitePage.jsx'

import TradePage from './pages/TradePage.jsx'

function pageFromHash() {
  const raw = (window.location.hash || '#home').replace(/^#/, '')
  if (['home', 'compare', 'snapshot', 'pairs', 'trade', 'suite'].includes(raw)) return raw
  return 'home'
}

export default function App() {
  const [page, setPage] = useState(pageFromHash)

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    const want = `#${page}`
    if (window.location.hash !== want) window.location.hash = page
  }, [page])

  let body = <HomePage />
  if (page === 'compare') body = <ComparePage />
  if (page === 'snapshot') body = <SnapshotPage />
  if (page === 'pairs') body = <PairLabPage />
  if (page === 'suite') body = <PairSuitePage />
  if (page === 'trade') body = <TradePage />

  return (
    <div className="lab-app">
      <Nav page={page} setPage={setPage} />
      <main className="lab-main">{body}</main>
      <footer className="lab-footer">
        Experimental UI · JM FX production desk unchanged ·{' '}
        <a href="/fx/">/fx/</a>
      </footer>
    </div>
  )
}
