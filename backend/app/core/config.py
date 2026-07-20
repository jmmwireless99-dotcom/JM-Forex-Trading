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
    max_daily_loss_pct: float = 2.0
    # Fallback stops if a strategy does not supply ATR levels (gold points)
    # pip=0.1 → 55 pips = $5.5 move on XAUUSD
    default_stop_loss_pips: float = 55.0
    default_take_profit_pips: float = 90.0

    # Market simulation — gold-only desk
    tick_interval_seconds: float = 1.0
    default_symbols: str = "XAUUSD"
    # auto_gold = automatic day/session/regime strategy switching
    default_strategy: str = "auto_gold"
    auto_strategy: bool = True
    # Avoid flip-flopping between strategies / overtrading paper noise
    strategy_stick_seconds: int = 900
    entry_cooldown_seconds: int = 300
    # Chart candles (M1) vs signal timeframe for entries (M5)
    candle_period_seconds: int = 60
    signal_period_seconds: int = 300
    candle_history: int = 240

    # Live gold: enable session + keep news filter on
    # JM_SESSION_FILTER=true  JM_NEWS_FILTER=true  JM_PRIME_SESSION_ONLY=false
    session_filter: bool = False
    news_filter: bool = True
    prime_session_only: bool = False
    # true = Asia PH 7AM–7PM only (flat after). false = full map (Asia → London → NY)
    # JM_ASIA_DESK_ONLY=false
    asia_desk_only: bool = False

    # MetaTrader file bridge (empty = paper only)
    # JM_MT4_BRIDGE_DIR or JM_MT5_BRIDGE_DIR =
    #   C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\Common\Files
    # JM_EXECUTION_MODE=paper|mt4|mt5
    execution_mode: str = "paper"
    mt4_bridge_dir: str = ""
    mt5_bridge_dir: str = ""
    mt4_symbol: str = "XAUUSD"
    mt_symbol: str = "XAUUSD"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
