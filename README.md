# JM Forex — Gold (XAUUSD) Automation

Paper-trading automation desk focused on **Gold vs USD (XAUUSD)**.

## Best strategy for us (recommended)

**`gold_confluence`** — session + news + indicator confluence.

| Layer | Rule | Why for gold |
| --- | --- | --- |
| **Session** | Trade London/NY (`07–20 UTC`), prefer **overlap `13–16 UTC`** | Best liquidity; Asia = fake breaks |
| **News** | Blackout **45m before / 30m after** NFP, CPI, FOMC-style USD prints | Gold spikes on USD data — automation should stand aside |
| **Trend** | EMA **21 / 55** | Direction filter |
| **Strength** | ADX **14 ≥ 22** | Skip chop |
| **Pullback** | RSI **14** in value zone (buy 40–55 / sell 45–60) + reclaim EMA21 | Don’t chase stretched gold |
| **Risk** | ATR **1.8× SL / 2.7× TP**, **0.5%/trade**, **1 position**, **2% daily loss** | Volatility-adaptive |

### Session map (UTC)

- **PRIME:** 13:00–16:00 — London/NY overlap  
- **ALLOWED:** 07:00–13:00 London · 16:00–20:00 NY  
- **AVOID:** Asia / weekend  

### News we respect

- NFP (first Friday)  
- CPI window  
- FOMC decision window  
- Core PCE window  

Enable live gates:

```bash
export JM_SESSION_FILTER=true
export JM_NEWS_FILTER=true
export JM_PRIME_SESSION_ONLY=false   # true = overlap only
export JM_DEFAULT_STRATEGY=gold_confluence
```

Secondary strategies (`gold_atr_trend`, `ema_crossover`, `rsi_mean_reversion`) stay available for comparison — **desk default is `gold_confluence`**.

## Quick start

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

- API: http://localhost:8000  
- Dashboard: http://localhost:5173  
- Desk filters: `GET /api/desk`

## Tests

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Layout

```
backend/app/strategies/
  gold_confluence.py   # recommended stack
  session.py           # London / NY / prime
  news_calendar.py     # USD news blackout
  indicators.py        # EMA, ATR, RSI, ADX
  gold_atr_trend.py    # simpler ATR fallback
```

> Paper mode only — no live broker orders in this build.
