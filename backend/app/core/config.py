from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JM_", env_file=".env", extra="ignore")

    app_name: str = "JM Forex"
    environment: str = "development"
    api_prefix: str = "/api"

    # Paper trading account
    initial_balance: float = 10_000.0
    base_currency: str = "USD"

    # Risk defaults
    max_risk_per_trade_pct: float = 1.0
    max_open_positions: int = 5
    max_daily_loss_pct: float = 3.0
    default_stop_loss_pips: float = 20.0
    default_take_profit_pips: float = 40.0

    # Market simulation
    tick_interval_seconds: float = 1.0
    default_symbols: str = "EURUSD,GBPUSD,USDJPY,XAUUSD"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_symbols.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()