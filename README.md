# JM Forex — Gold (XAUUSD) Automation

Paper-trading automation desk focused on **Gold vs USD (XAUUSD)**.

## Recommended setup (default)

| Setting | Value | Why |
| --- | --- | --- |
| **Symbol** | `XAUUSD` only | Focus + cleaner risk |
| **Strategy** | `gold_atr_trend` | Gold trends hard; fixed-pip stops fail in its volatility |
| **Risk / trade** | `0.5%` | Gold expands fast — keep per-trade damage small |
| **Max positions** | `1` | One gold idea at a time |
| **Daily loss cap** | `2%` | Hard kill-switch for bad sessions |
| **Stops / targets** | `1.8×ATR` SL · `2.7×ATR` TP (~1.5R) | Volatility-adaptive, not fixed dollars |
| **Session (live)** | London/NY `07–20 UTC` | Best liquidity; avoid thin Asian spikes |

### Why ATR trend-pullback (not plain EMA cross / RSI)?

1. **Gold is a trend + volatility instrument** — it runs, then mean-reverts violently. Naked EMA crosses get chopped; pure RSI fades get run over in breakouts.
2. **ATR stops scale with the day** — a $3 stop on a $12 ATR day is noise; ATR sizing fixes that.
3. **Pullback entries** — trade with the EMA21/EMA55 trend, enter when price comes back to the fast EMA after a stretch (better R:R than chasing).
4. **Session filter (live)** — most clean gold moves print in London/NY. Enable with `JM_SESSION_FILTER=true`.

Secondary strategies (`ema_crossover`, `rsi_mean_reversion`) remain available for comparison, but **`gold_atr_trend` is the desk default**.

## Quick start

```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

- API: http://localhost:8000  
- Dashboard: http://localhost:5173  

## Config (gold desk)

```bash
export JM_DEFAULT_SYMBOLS=XAUUSD
export JM_DEFAULT_STRATEGY=gold_atr_trend
export JM_MAX_RISK_PER_TRADE_PCT=0.5
export JM_MAX_OPEN_POSITIONS=1
export JM_MAX_DAILY_LOSS_PCT=2.0
export JM_SESSION_FILTER=true   # enable for live London/NY only
```

## Tests

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Project layout

```
backend/app/
  strategies/gold_atr_trend.py   # recommended XAUUSD strategy
  engine/                        # orchestration loop
  risk/                          # hard risk gates
  brokers/                       # paper broker (100oz gold contract) + tick sim
  api/                           # REST + WebSocket
frontend/                        # JM Forex gold desk UI
```

## Live next steps

1. Replace `MarketDataSimulator` with a real XAUUSD feed  
2. Add broker adapter (MT5 / cTrader / REST) behind the same interface  
3. Keep `JM_SESSION_FILTER=true` and skip high-impact USD events (NFP, FOMC) when you add a calendar gate  

> This build is **paper mode only**. No live broker orders are placed.
