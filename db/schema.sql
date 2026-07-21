-- JM Forex — XAUUSD Scalping Engine schema (PostgreSQL)
-- Reviewed & hardened from Gemini draft:
--   * UNIQUE (symbol, timeframe, timestamp) on candles
--   * UNIQUE strategies.name
--   * timeframe + strategy_id extras for signals/trades
--   * gold-friendly NUMERIC scales
--   * indexes on symbol / status / timestamp

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN
    CREATE TYPE zone_type AS ENUM (
        'ASIAN_HIGH', 'ASIAN_LOW', 'PDH', 'PDL',
        'SUPPLY_ZONE', 'DEMAND_ZONE', 'FVG', 'ORDER_BLOCK'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE signal_side AS ENUM ('BUY', 'SELL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE signal_status AS ENUM ('PENDING', 'EXECUTED', 'CANCELLED', 'EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE trade_side AS ENUM ('BUY', 'SELL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE trade_status AS ENUM (
        'OPEN', 'CLOSED_TP', 'CLOSED_SL', 'CLOSED_MANUAL', 'REJECTED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- A. strategies
CREATE TABLE IF NOT EXISTS strategies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(64) NOT NULL UNIQUE,
    timeframe       VARCHAR(8) NOT NULL DEFAULT 'M5',
    parameters      JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_strategies_active ON strategies (is_active);

-- B. market_data_candles
CREATE TABLE IF NOT EXISTS market_data_candles (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(16) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    open            NUMERIC(14, 5) NOT NULL,
    high            NUMERIC(14, 5) NOT NULL,
    low             NUMERIC(14, 5) NOT NULL,
    close           NUMERIC(14, 5) NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_candles_symbol_tf_ts UNIQUE (symbol, timeframe, timestamp),
    CONSTRAINT ck_candles_ohlc CHECK (high >= low AND high >= open AND high >= close AND low <= open AND low <= close)
);

CREATE INDEX IF NOT EXISTS ix_candles_symbol_tf_ts
    ON market_data_candles (symbol, timeframe, timestamp DESC);

-- C. liquidity_zones_and_fvgs (SMC)
CREATE TABLE IF NOT EXISTS liquidity_zones_and_fvgs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          VARCHAR(16) NOT NULL DEFAULT 'XAUUSD',
    timeframe       VARCHAR(8) NOT NULL DEFAULT 'M5',
    zone_type       zone_type NOT NULL,
    price_high      NUMERIC(14, 5) NOT NULL,
    price_low       NUMERIC(14, 5) NOT NULL,
    is_swept        BOOLEAN NOT NULL DEFAULT FALSE,
    swept_at        TIMESTAMPTZ,
    is_mitigated    BOOLEAN NOT NULL DEFAULT FALSE,
    mitigated_at    TIMESTAMPTZ,
    origin_time     TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_zone_prices CHECK (price_high >= price_low)
);

CREATE INDEX IF NOT EXISTS ix_zones_symbol_type
    ON liquidity_zones_and_fvgs (symbol, zone_type);
CREATE INDEX IF NOT EXISTS ix_zones_unswept
    ON liquidity_zones_and_fvgs (symbol, is_swept)
    WHERE is_swept = FALSE;

-- D. signals
CREATE TABLE IF NOT EXISTS signals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id         UUID REFERENCES strategies (id) ON DELETE SET NULL,
    symbol              VARCHAR(16) NOT NULL DEFAULT 'XAUUSD',
    timeframe           VARCHAR(8) NOT NULL DEFAULT 'M5',
    signal_type         signal_side NOT NULL,
    entry_price         NUMERIC(14, 5) NOT NULL,
    stop_loss           NUMERIC(14, 5) NOT NULL,
    take_profit         NUMERIC(14, 5) NOT NULL,
    risk_reward_ratio   NUMERIC(8, 3),
    status              signal_status NOT NULL DEFAULT 'PENDING',
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_signals_strategy ON signals (strategy_id);
CREATE INDEX IF NOT EXISTS ix_signals_status ON signals (status);
CREATE INDEX IF NOT EXISTS ix_signals_symbol_created
    ON signals (symbol, created_at DESC);

-- E. trades
CREATE TABLE IF NOT EXISTS trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id       UUID REFERENCES signals (id) ON DELETE SET NULL,
    strategy_id     UUID REFERENCES strategies (id) ON DELETE SET NULL,
    symbol          VARCHAR(16) NOT NULL DEFAULT 'XAUUSD',
    order_type      trade_side NOT NULL,
    lot_size        NUMERIC(10, 4) NOT NULL,
    open_price      NUMERIC(14, 5) NOT NULL,
    close_price     NUMERIC(14, 5),
    stop_loss       NUMERIC(14, 5),
    take_profit     NUMERIC(14, 5),
    pnl_amount      NUMERIC(14, 4),
    pips_gained     NUMERIC(12, 2),
    status          trade_status NOT NULL DEFAULT 'OPEN',
    ticket          VARCHAR(64),
    mode            VARCHAR(16) NOT NULL DEFAULT 'paper',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_trades_status ON trades (status);
CREATE INDEX IF NOT EXISTS ix_trades_symbol_opened ON trades (symbol, opened_at DESC);
CREATE INDEX IF NOT EXISTS ix_trades_signal ON trades (signal_id);
CREATE INDEX IF NOT EXISTS ix_trades_ticket ON trades (ticket);

-- updated_at trigger helper
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_strategies_updated ON strategies;
CREATE TRIGGER trg_strategies_updated
    BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_zones_updated ON liquidity_zones_and_fvgs;
CREATE TRIGGER trg_zones_updated
    BEFORE UPDATE ON liquidity_zones_and_fvgs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_signals_updated ON signals;
CREATE TRIGGER trg_signals_updated
    BEFORE UPDATE ON signals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_trades_updated ON trades;
CREATE TRIGGER trg_trades_updated
    BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
