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
    default_stop_loss_pips: float = 35.0  # 3.5 USD when pip=0.1
    default_take_profit_pips: float = 70.0

    # Market simulation — gold-only desk
    tick_interval_seconds: float = 1.0
    default_symbols: str = "XAUUSD"
    default_strategy: str = "gold_confluence"

    # Live gold: enable session + keep news filter on
    # JM_SESSION_FILTER=true  JM_NEWS_FILTER=true  JM_PRIME_SESSION_ONLY=false
    session_filter: bool = False
    news_filter: bool = True
    prime_session_only: bool = False

    # MT4 file bridge (empty = paper only)
    # Windows example:
    # JM_MT4_BRIDGE_DIR=C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\Common\Files
    # JM_EXECUTION_MODE=mt4
    execution_mode: str = "paper"  # paper | mt4
    mt4_bridge_dir: str = ""
    mt4_symbol: str = "XAUUSD"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
