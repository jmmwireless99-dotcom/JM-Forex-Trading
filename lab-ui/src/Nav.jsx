export function Link({ to, className = '', children, ...props }) {
  return (
    <a
      href={`#${to}`}
      className={className}
      onClick={(e) => {
        e.preventDefault()
        window.location.hash = to
      }}
      {...props}
    >
      {children}
    </a>
  )
}

export default function Nav({ page, setPage }) {
  const tabs = [
    { id: 'home', label: 'Home' },
    { id: 'trade', label: 'Live demo' },
    { id: 'suite', label: '5-pair test' },
    { id: 'compare', label: 'Compare' },
    { id: 'snapshot', label: 'JM FX snapshot' },
    { id: 'pairs', label: 'Pair lab' },
  ]

  return (
    <header className="lab-nav">
      <div className="lab-nav-inner">
        <a href="#home" className="lab-brand" onClick={(e) => { e.preventDefault(); setPage('home') }}>
          JM <span>Lab</span>
        </a>
        <nav className="lab-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              className={page === t.id ? 'on' : ''}
              onClick={() => setPage(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <a href="/fx/" className="lab-desk-link">
          JM FX desk ↗
        </a>
      </div>
    </header>
  )
}
