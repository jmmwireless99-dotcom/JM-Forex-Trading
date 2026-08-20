import { useState } from 'react'
import { PAIR_EXPERIMENTS } from '../data/compare.js'

const NOTES_KEY = 'jm_lab_pair_notes'

function loadNotes() {
  try {
    return JSON.parse(localStorage.getItem(NOTES_KEY) || '{}')
  } catch {
    return {}
  }
}

export default function PairLabPage() {
  const [selected, setSelected] = useState('EURUSD')
  const [notes, setNotes] = useState(loadNotes)
  const [draft, setDraft] = useState(notes.EURUSD || '')

  const pair = PAIR_EXPERIMENTS.find((p) => p.id === selected) || PAIR_EXPERIMENTS[0]

  function selectPair(id) {
    setSelected(id)
    setDraft(notes[id] || '')
  }

  function saveNote() {
    const next = { ...notes, [selected]: draft }
    setNotes(next)
    try {
      localStorage.setItem(NOTES_KEY, JSON.stringify(next))
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="lab-page">
      <header className="lab-page-head">
        <h1>Pair sandbox</h1>
        <p className="lab-muted">
          Future home for EUR/USD and other pair bots. No connection to JM FX engine yet.
        </p>
      </header>

      <div className="lab-pair-bar">
        {PAIR_EXPERIMENTS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={selected === p.id ? 'on' : ''}
            onClick={() => selectPair(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <section className="lab-panel">
        <div className="lab-pair-head">
          <h2>{pair.label}</h2>
          <span className={`lab-tag lab-tag-${pair.status}`}>{pair.status}</span>
        </div>
        <p>{pair.note}</p>

        {pair.id === 'XAUUSD' ? (
          <div className="lab-callout lab-callout-sm">
            Gold is traded on the production JM FX desk. Use{' '}
            <a href="/fx/" className="lab-link">
              Trading Desk
            </a>{' '}
            or the Lab snapshot page for live data.
          </div>
        ) : (
          <div className="lab-placeholder-chart" aria-hidden="true">
            <p>Chart + strategy engine — coming in lab backend v1</p>
            <p className="lab-muted">Planned: ECN spread check · demo paper · separate service</p>
          </div>
        )}
      </section>

      <section className="lab-panel">
        <h2>Experiment notes (local)</h2>
        <p className="lab-muted">Saved in this browser only — not synced to JM FX.</p>
        <textarea
          className="lab-notes"
          rows={5}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Backtest results, spread observations, broker notes…"
        />
        <button type="button" className="lab-btn" onClick={saveNote}>
          Save note
        </button>
      </section>
    </div>
  )
}
