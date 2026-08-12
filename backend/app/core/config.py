from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JM_", env_file=".env", extra="ignore")

    app_name: str = "JM Forex"
    environment: str = "development"
    api_prefix: str = "/api"
    # Production: directory with Vite build (index.html + assets/)
    static_dir: str = ""
    portal_url: str = "https://jmtechsolution.cloud"

    # Paper trading account
    initial_balance: float = 10_000.0
    base_currency: str = "USD"

    # Gold desk risk defaults — tighter than multi-pair FX
    max_risk_per_trade_pct: float = 0.5
    max_open_positions: int = 1
    max_daily_loss_pct: float = 0.0  # 0 = disabled (no daily loss kill-switch)

    # Fallback stops if a strategy does not supply ATR levels (gold points)
    # pip=0.1 → 55 pips = $5.5 move on XAUUSD
    default_stop_loss_pips: float = 55.0
    default_take_profit_pips: float = 90.0

    # Market simulation — gold-only desk
    tick_interval_seconds: float = 1.0
    default_symbols: str = "XAUUSD"
    # Scalp desk: session auto-follow on by default
    # JM_DEFAULT_STRATEGY=manual_only  JM_AUTO_STRATEGY=true
    default_strategy: str = "manual_only"
    auto_strategy: bool = True
    # Avoid flip-flopping between strategies / overtrading paper noise
    strategy_stick_seconds: int = 300
    entry_cooldown_seconds: int = 120
    # Chart candles (M1) vs signal timeframe for entries (M5)
    candle_period_seconds: int = 60
    signal_period_seconds: int = 300
    candle_history: int = 240

    # Live gold: enable session + keep news filter on
    # JM_SESSION_FILTER=true  JM_NEWS_FILTER=true  JM_PRIME_SESSION_ONLY=false
    session_filter: bool = False
    news_filter: bool = True
    prime_session_only: bool = False
    # true = Asia PH 7AM–5PM only (flat after). false = full map (Asia → London → NY)
    # JM_ASIA_DESK_ONLY=false
    asia_desk_only: bool = False

    # Paper tape: pin XAUUSD mid to live gold (Yahoo GC=F / Binance PAXG)
    # so Manual trade / desk match TradingView (~4100), not the old 2350 sim.
    # JM_PAPER_SYNC_LIVE_GOLD=true
    paper_sync_live_gold: bool = True
    paper_live_noise: float = 0.08  # small jitter around live mid (points)

    # MetaTrader file bridge (empty = paper only)
    # JM_MT4_BRIDGE_DIR or JM_MT5_BRIDGE_DIR =
    #   C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\Common\Files
    # JM_EXECUTION_MODE=paper|mt4|mt5
    execution_mode: str = "paper"
    mt4_bridge_dir: str = ""
    mt5_bridge_dir: str = ""
    mt4_symbol: str = "XAUUSD"
    mt_symbol: str = "XAUUSD"

    # Postgres persistence (empty = in-memory only, desk still works)
    # JM_DATABASE_URL=postgresql+psycopg://jm:jm@127.0.0.1:5432/jm_forex
    database_url: str = ""
    database_auto_migrate: bool = True
    database_seed_on_boot: bool = True

    # AI / ML trade assist — records history + scores setups before entry
    # JM_AI_ASSIST=true  JM_AI_GATE_ENTRIES=true
    ai_assist: bool = True
    ai_gate_entries: bool = True
    ai_min_win_prob: float = 0.40
    ai_skip_confidence: float = 0.55
    ai_history_path: str = "data/ai_trade_history.jsonl"
    ai_model_path: str = "data/ai_trade_model.json"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
