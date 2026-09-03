/** Pair → lab auto strategy preset (mirrors lab-backend/app/pair_strategies.py) */
export const PAIR_PRESETS = {
  EURUSD: {
    strategy: 'EMA_RSI_SCALP',
    lots: 0.01,
    sl_pips: 12,
    tp_pips: 24,
    label: 'Scalper · EMA+RSI',
    botStyle: 'Best overall · Scalper · General EA',
  },
  GBPUSD: {
    strategy: 'BREAKOUT',
    lots: 0.01,
    sl_pips: 18,
    tp_pips: 36,
    label: 'Breakout · 24-bar range',
    botStyle: 'Trend follower · Breakout',
  },
  AUDNZD: {
    strategy: 'MEAN_REVERT',
    lots: 0.01,
    sl_pips: 14,
    tp_pips: 20,
    label: 'Mean revert · range edges',
    botStyle: 'Grid · Mean reversion · Range',
  },
  EURCHF: {
    strategy: 'MEAN_REVERT',
    lots: 0.01,
    sl_pips: 10,
    tp_pips: 16,
    label: 'Mean revert · Asian range',
    botStyle: 'Grid · Asian session scalper',
  },
  XAUUSD: {
    strategy: 'EMA_RSI_TREND',
    lots: 0.03,
    sl_pips: 20,
    tp_pips: 40,
    label: 'Gold scalper · EMA+RSI',
    botStyle: 'Trend · M5 scalper (lab paper)',
  },
}

export const STRATEGY_INFO = {
  EMA_RSI_SCALP: {
    name: 'EMA+RSI Scalper',
    description: 'M5 EMA 20/50 + RSI — buy zone 40–54, sell 46–60. Best for EUR/USD.',
  },
  BREAKOUT: {
    name: 'Range Breakout',
    description: 'M5 close breaks 24-bar high or low. Built for GBP/USD volatility.',
  },
  MEAN_REVERT: {
    name: 'Mean Reversion',
    description: 'Buy bottom 25% / sell top 25% of range. Grid-lite for AUD/NZD & EUR/CHF.',
  },
  EMA_RSI_TREND: {
    name: 'Gold EMA+RSI Scalper',
    description: 'M5 EMA 20/50 + RSI 14 — wider zones (35–56 buy, 42–65 sell). Paper lab only.',
  },
}

export const BOT_ROWS = [
  {
    id: 'jmfx',
    name: 'JM FX (Gold)',
    symbol: 'XAUUSD',
    type: 'Session scalp + ML',
    spread: 'Higher',
    session: 'PH schedule (7AM–8:30PM EMA, evening SMC)',
    blowUp: 'Low–medium',
    martingale: 'No',
    verdict: 'Production desk — do not modify from Lab',
    highlight: true,
  },
  {
    id: 'scalper',
    name: 'Generic Scalper EA',
    symbol: 'EUR/USD',
    type: 'Tick / M5 scalp',
    spread: 'Very low (best on ECN)',
    session: 'London / NY overlap',
    blowUp: 'Medium',
    martingale: 'Rare',
    verdict: 'Lab: EMA+RSI Scalper auto',
    highlight: false,
  },
  {
    id: 'grid',
    name: 'Grid / Mean revert EA',
    symbol: 'AUD/NZD, EUR/CHF',
    type: 'Range / mean reversion',
    spread: 'Medium',
    session: 'Quiet hours (Asian)',
    blowUp: 'Very high',
    martingale: 'No in Lab',
    verdict: 'Lab: Mean Reversion auto (demo)',
    highlight: false,
  },
  {
    id: 'trend',
    name: 'Trend / Breakout EA',
    symbol: 'GBP/USD, XAUUSD',
    type: 'Trend follow / breakout',
    spread: 'Medium',
    session: 'London open, NY',
    blowUp: 'Medium',
    martingale: 'No',
    verdict: 'Lab: Breakout + EMA trend auto',
    highlight: false,
  },
]

const PAIR_LABELS = {
  EURUSD: 'EUR/USD',
  GBPUSD: 'GBP/USD',
  AUDNZD: 'AUD/NZD',
  EURCHF: 'EUR/CHF',
  XAUUSD: 'XAUUSD (Gold)',
}

export const PAIR_GUIDE = Object.entries(PAIR_PRESETS).map(([id, p]) => ({
  id,
  label: PAIR_LABELS[id] || id,
  botStyle: p.botStyle,
  spread: id === 'EURUSD' ? 'Very low (ECN ideal)' : id === 'XAUUSD' ? 'Higher' : 'Medium',
  session:
    id === 'AUDNZD' || id === 'EURCHF'
      ? 'Asian · quiet hours'
      : id === 'GBPUSD'
        ? 'London open · NY volatility'
        : id === 'XAUUSD'
          ? '24h · M5 scalper'
          : 'London / NY',
  labAuto: p.label,
  strategy: p.strategy,
  sl_pips: p.sl_pips,
  tp_pips: p.tp_pips,
  risk: id === 'AUDNZD' || id === 'EURCHF' ? 'Medium (demo)' : id === 'GBPUSD' ? 'Medium' : 'Low–medium',
  status: 'live',
  note:
    id === 'EURUSD'
      ? '#1 liquidity — auto scalper preset applied on Start auto.'
      : id === 'GBPUSD'
        ? 'Breakout auto on each new M5 bar when flat.'
        : id === 'AUDNZD'
          ? 'Mean revert at range edges — no martingale, max 1 position.'
          : id === 'EURCHF'
            ? 'Tighter Asian range mean revert preset.'
            : 'Gold M5 scalper — separate from JM FX production desk at /fx/.',
}))

export const PAIR_EXPERIMENTS = PAIR_GUIDE

export const LAB_TIPS = [
  'Each pair auto-loads its own strategy when you click Start auto.',
  'Use ECN / raw-spread broker on live — bots die on wide spreads.',
  'Run bots on VPS 24/7 — Lab server keeps auto running.',
  'Backtest weeks of demo before real money.',
  'JM Lab = paper only. JM FX gold desk = /fx/.',
]
