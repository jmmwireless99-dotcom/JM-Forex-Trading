/** Pairs in the lab suite dashboard (mirrors lab-backend PAIR_SUITE_SYMBOLS) */
export const SUITE_PAIRS = ['EURUSD', 'GBPUSD', 'AUDNZD', 'EURCHF', 'XAUUSD']

/** Pair → lab auto strategy preset (mirrors lab-backend/app/pair_strategies.py) */
export const PAIR_PRESETS = {
  EURUSD: {
    strategy: 'EMA_RSI_SCALP',
    lots: 0.01,
    sl_pips: 14,
    tp_pips: 28,
    label: 'Scalper · EMA+RSI',
    botStyle: 'Best overall · Scalper · General EA',
  },
  GBPUSD: {
    strategy: 'BREAKOUT',
    lots: 0.01,
    sl_pips: 20,
    tp_pips: 40,
    label: 'Breakout · 24-bar range',
    botStyle: 'Trend follower · Breakout',
  },
  AUDNZD: {
    strategy: 'MEAN_REVERT',
    lots: 0.01,
    sl_pips: 16,
    tp_pips: 32,
    label: 'Mean revert · range edges',
    botStyle: 'Grid · Mean reversion · Range',
  },
  EURCHF: {
    strategy: 'MEAN_REVERT',
    lots: 0.01,
    sl_pips: 14,
    tp_pips: 28,
    label: 'Mean revert · filtered',
    botStyle: 'Grid · Asian session scalper',
  },
  XAUUSD: {
    strategy: 'EMA_RSI_TREND',
    lots: 0.01,
    sl_pips: 45,
    tp_pips: 90,
    label: 'Trend · EMA+RSI gold',
    botStyle: 'Trend · Session scalp',
  },
}

export const STRATEGY_INFO = {
  EMA_RSI_SCALP: {
    name: 'EMA+RSI Scalper',
    description: 'M5 EMA 20/50 + RSI + candle confirm. SL/TP from fill price.',
  },
  BREAKOUT: {
    name: 'Range Breakout',
    description: 'M5 close breaks 24-bar range with buffer — fewer false breaks.',
  },
  MEAN_REVERT: {
    name: 'Mean Reversion',
    description: 'Fade range edges only with trend filter + rejection bar. Cooldown after loss.',
  },
  EMA_RSI_TREND: {
    name: 'EMA+RSI Trend',
    description: 'Gold: wider 45/90 pip SL/TP, 4-bar spacing, no chase on overbought RSI.',
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
          ? 'JM FX Manila schedule'
          : 'London / NY',
  labAuto: p.label,
  strategy: p.strategy,
  sl_pips: p.sl_pips,
  tp_pips: p.tp_pips,
  risk: id === 'AUDNZD' || id === 'EURCHF' ? 'Medium (demo)' : id === 'GBPUSD' ? 'Medium' : 'Low–medium',
  status: id === 'XAUUSD' ? 'live-ref' : 'live',
  note:
    id === 'EURUSD'
      ? '#1 liquidity — auto scalper preset applied on Start auto.'
      : id === 'GBPUSD'
        ? 'Breakout auto on each new M5 bar when flat.'
        : id === 'AUDNZD'
          ? 'Mean revert at range edges — no martingale, max 1 position.'
          : id === 'EURCHF'
            ? 'Tighter Asian range mean revert preset.'
            : 'EMA+RSI trend preset — production desk at /fx/.',
}))

export const PAIR_EXPERIMENTS = PAIR_GUIDE

export const LAB_TIPS = [
  'Each pair auto-loads its own strategy when you click Start auto.',
  'Use ECN / raw-spread broker on live — bots die on wide spreads.',
  'Run bots on VPS 24/7 — Lab server keeps auto running.',
  'Backtest weeks of demo before real money.',
  'JM Lab = paper only. JM FX gold desk = /fx/.',
]
