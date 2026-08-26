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
    # pip=0.1 → 90 pips = $9.00 move on XAUUSD; TP at 2.5R = 225 pips ($22.50)
    default_stop_loss_pips: float = 90.0
    default_take_profit_pips: float = 225.0

    # Market simulation — gold-only desk
    tick_interval_seconds: float = 1.0
    default_symbols: str = "XAUUSD"
    # Scalp desk: AI_ML auto-follow on by default
    # JM_DEFAULT_STRATEGY=AI_ML  JM_AUTO_STRATEGY=true
    default_strategy: str = "AI_ML"
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
    # true = Asia PH 7AM–8PM only (flat after). false = full map (Asia → London → NY)
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

    # AI & Machine Learning — records history + ML scores setups before entry
    # JM_AI_ASSIST=true  JM_AI_GATE_ENTRIES=true
    ai_assist: bool = True
    ai_gate_entries: bool = True
    ai_min_win_prob: float = 0.40
    ai_skip_confidence: float = 0.55
    ai_history_path: str = "data/ai_trade_history.jsonl"
    ai_model_path: str = "data/ai_trade_model.json"
    # Safety: block SMC SELL overlap only after enough weak labeled samples
    # (cold-start is allowed so overlap is not permanently frozen)
    ai_block_smc_sell_overlap: bool = True
    ai_smc_sell_overlap_min_wr: float = 0.35
    ai_smc_sell_overlap_min_n: int = 5

    # Auto signal routing — false = one desk signal fills every follow_auto account
    auto_fill_single_book: bool = False
    # Optional: pin fills to this account code; else earliest auto-follower
    auto_fill_account_code: str = ""

    # Investment dashboard (30% / 30 days default yield model)
    invest_secret: str = "jm-fx-invest-dev-secret-change-me"
    invest_admin_email: str = "admin@jmfx.local"
    invest_admin_password: str = "admin123"
    invest_admin_name: str = "JM FX Admin"
    invest_demo_enabled: bool = False
    invest_demo_email: str = "demo@jmfx.local"
    invest_demo_password: str = "demo1234"
    invest_demo_name: str = "Demo Investor"
    invest_demo_deposit: float = 1000.0
    invest_demo_backdate_days: int = 7
    invest_period_rate: float = 0.30
    invest_period_days: int = 30

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
