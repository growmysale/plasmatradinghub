"""PropEdge Database Layer.

DuckDB for analytics (columnar, fast aggregations).
SQLite for operational state (current positions, active orders).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

from core.config import get_config

logger = logging.getLogger(__name__)


# ── DuckDB Schema ────────────────────────────────────────────────────────

DUCKDB_SCHEMA = """
-- Raw candle data
CREATE TABLE IF NOT EXISTS candles (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE DEFAULT 0,
    tick_count INTEGER DEFAULT 0,
    vwap DOUBLE DEFAULT 0,
    buy_volume DOUBLE DEFAULT 0,
    sell_volume DOUBLE DEFAULT 0,
    delta DOUBLE DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Pre-computed feature vectors (Feature Store)
CREATE TABLE IF NOT EXISTS features (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    feature_json VARCHAR,
    regime VARCHAR,
    regime_confidence DOUBLE,
    market_structure VARCHAR,
    vwap_distance_atr DOUBLE,
    ema20_distance_atr DOUBLE,
    rsi_14 DOUBLE,
    atr_14 DOUBLE,
    volume_ratio DOUBLE,
    is_kill_zone BOOLEAN,
    kill_zone_name VARCHAR,
    minutes_to_news INTEGER,
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Every signal from every agent
CREATE TABLE IF NOT EXISTS agent_signals (
    id VARCHAR PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    agent_id VARCHAR NOT NULL,
    agent_version VARCHAR,
    symbol VARCHAR NOT NULL,
    direction VARCHAR,
    confidence DOUBLE,
    entry_price DOUBLE,
    stop_loss DOUBLE,
    take_profit DOUBLE,
    risk_reward_ratio DOUBLE,
    features_snapshot VARCHAR,
    reasoning VARCHAR,
    was_taken BOOLEAN DEFAULT FALSE,
    outcome_if_taken DOUBLE,
    actual_pnl DOUBLE,
    regime_at_signal VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Executed trade log
CREATE TABLE IF NOT EXISTS trades (
    id VARCHAR PRIMARY KEY,
    ts_open TIMESTAMP NOT NULL,
    ts_close TIMESTAMP,
    symbol VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    entry_price DOUBLE NOT NULL,
    exit_price DOUBLE,
    quantity INTEGER NOT NULL DEFAULT 1,
    stop_loss DOUBLE,
    take_profit DOUBLE,
    pnl DOUBLE,
    pnl_ticks DOUBLE,
    commission DOUBLE DEFAULT 0,
    slippage_ticks DOUBLE,
    agent_signals_used VARCHAR,
    combined_confidence DOUBLE,
    position_size_reason VARCHAR,
    regime VARCHAR,
    market_structure VARCHAR,
    session VARCHAR,
    vwap_position VARCHAR,
    atr_at_entry DOUBLE,
    features_at_entry VARCHAR,
    manual_override BOOLEAN DEFAULT FALSE,
    override_reason VARCHAR,
    emotion_tag VARCHAR,
    followed_system BOOLEAN DEFAULT TRUE,
    account_balance_before DOUBLE,
    account_balance_after DOUBLE,
    max_loss_limit_distance DOUBLE,
    daily_pnl_before DOUBLE,
    daily_pnl_after DOUBLE,
    intended_entry DOUBLE,
    actual_entry DOUBLE,
    entry_slippage DOUBLE,
    intended_exit DOUBLE,
    actual_exit DOUBLE,
    exit_slippage DOUBLE,
    mode VARCHAR DEFAULT 'sandbox',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent performance tracking
CREATE TABLE IF NOT EXISTS agent_performance (
    agent_id VARCHAR NOT NULL,
    date DATE NOT NULL,
    signals_generated INTEGER DEFAULT 0,
    signals_taken INTEGER DEFAULT 0,
    signals_profitable INTEGER DEFAULT 0,
    signal_accuracy DOUBLE,
    avg_confidence DOUBLE,
    total_pnl DOUBLE,
    win_rate DOUBLE,
    profit_factor DOUBLE,
    avg_win DOUBLE,
    avg_loss DOUBLE,
    max_drawdown DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    expectancy DOUBLE,
    current_weight DOUBLE,
    weight_trend VARCHAR,
    oos_sharpe DOUBLE,
    oos_profit_factor DOUBLE,
    oos_win_rate DOUBLE,
    oos_degradation DOUBLE,
    PRIMARY KEY (agent_id, date)
);

-- Regime log
CREATE TABLE IF NOT EXISTS regime_log (
    ts TIMESTAMP PRIMARY KEY,
    regime VARCHAR NOT NULL,
    confidence DOUBLE,
    duration_minutes INTEGER,
    features_json VARCHAR,
    hmm_state INTEGER,
    volatility_percentile DOUBLE,
    trend_strength DOUBLE
);

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_results (
    id VARCHAR PRIMARY KEY,
    agent_id VARCHAR NOT NULL,
    run_timestamp TIMESTAMP NOT NULL,
    train_start DATE,
    train_end DATE,
    test_start DATE,
    test_end DATE,
    is_total_trades INTEGER,
    is_win_rate DOUBLE,
    is_profit_factor DOUBLE,
    is_sharpe DOUBLE,
    is_max_drawdown DOUBLE,
    is_expectancy DOUBLE,
    oos_total_trades INTEGER,
    oos_win_rate DOUBLE,
    oos_profit_factor DOUBLE,
    oos_sharpe DOUBLE,
    oos_max_drawdown DOUBLE,
    oos_expectancy DOUBLE,
    wf_num_windows INTEGER,
    wf_avg_oos_sharpe DOUBLE,
    wf_std_oos_sharpe DOUBLE,
    wf_pct_profitable_windows DOUBLE,
    wf_worst_window_sharpe DOUBLE,
    mc_median_return DOUBLE,
    mc_5th_percentile_return DOUBLE,
    mc_95th_percentile_return DOUBLE,
    mc_probability_of_ruin DOUBLE,
    p_value DOUBLE,
    is_significant BOOLEAN,
    vs_random_sharpe DOUBLE,
    vs_buy_hold_sharpe DOUBLE,
    params_json VARCHAR,
    model_path VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Strategy evolution tracker
CREATE TABLE IF NOT EXISTS strategy_evolution (
    generation INTEGER NOT NULL,
    individual_id VARCHAR NOT NULL,
    parent_ids VARCHAR,
    params_json VARCHAR NOT NULL,
    fitness_score DOUBLE,
    oos_sharpe DOUBLE,
    oos_profit_factor DOUBLE,
    oos_max_drawdown DOUBLE,
    survived BOOLEAN DEFAULT FALSE,
    promoted_to_agent BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (generation, individual_id)
);

-- Prop firm compliance ledger
CREATE TABLE IF NOT EXISTS compliance_log (
    ts TIMESTAMP NOT NULL,
    event_type VARCHAR NOT NULL,
    rule VARCHAR NOT NULL,
    current_value DOUBLE,
    limit_value DOUBLE,
    pct_used DOUBLE,
    action_taken VARCHAR,
    details VARCHAR
);

-- Daily session records
CREATE TABLE IF NOT EXISTS sessions (
    date DATE PRIMARY KEY,
    pre_market_bias VARCHAR,
    regime_at_open VARCHAR,
    key_levels_json VARCHAR,
    economic_events_json VARCHAR,
    agents_active_json VARCHAR,
    agent_weights_json VARCHAR,
    total_signals_generated INTEGER DEFAULT 0,
    total_signals_taken INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    total_pnl DOUBLE DEFAULT 0,
    best_agent VARCHAR,
    worst_agent VARCHAR,
    regime_changes INTEGER DEFAULT 0,
    compliance_warnings INTEGER DEFAULT 0,
    system_grade VARCHAR,
    override_count INTEGER DEFAULT 0,
    override_was_right INTEGER DEFAULT 0,
    notes VARCHAR,
    lessons VARCHAR
);

-- Event log (for replay and debugging)
CREATE TABLE IF NOT EXISTS event_log (
    ts TIMESTAMP NOT NULL,
    event_type VARCHAR NOT NULL,
    source VARCHAR,
    data_json VARCHAR
);
"""


class DuckDBManager:
    """DuckDB connection manager for analytics."""

    def __init__(self, db_path: Optional[str] = None):
        config = get_config()
        self.db_path = db_path or config.data.duckdb_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(self.db_path)
            self._init_schema()
        return self._conn

    def _init_schema(self):
        """Initialize all tables."""
        for statement in DUCKDB_SCHEMA.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    self._conn.execute(stmt)
                except Exception as e:
                    logger.warning(f"Schema init warning: {e}")

    def execute(self, query: str, params: Optional[list] = None):
        """Execute a query."""
        if params:
            return self.conn.execute(query, params)
        return self.conn.execute(query)

    def fetchall(self, query: str, params: Optional[list] = None) -> list:
        """Execute and fetch all results."""
        result = self.execute(query, params)
        return result.fetchall()

    def fetchdf(self, query: str, params: Optional[list] = None):
        """Execute and return as pandas DataFrame."""
        result = self.execute(query, params)
        return result.fetchdf()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()


class SQLiteManager:
    """SQLite manager for operational state."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS active_orders (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS positions (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS system_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS agent_registry (
        agent_id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        version TEXT DEFAULT '1.0',
        is_active INTEGER DEFAULT 1,
        params_json TEXT,
        preferred_regimes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    """

    def __init__(self, db_path: Optional[str] = None):
        config = get_config()
        self.db_path = db_path or config.data.sqlite_path
        self._init_db()

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_state(self, key: str, value: Any):
        """Set a system state value."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), datetime.now().isoformat()),
            )

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a system state value."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row["value"])
            return default

    def register_agent(self, agent_id: str, agent_name: str, agent_type: str,
                       params: Optional[dict] = None, preferred_regimes: Optional[list] = None):
        """Register a strategy agent."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO agent_registry
                   (agent_id, agent_name, agent_type, params_json, preferred_regimes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    agent_id, agent_name, agent_type,
                    json.dumps(params or {}),
                    json.dumps(preferred_regimes or []),
                    datetime.now().isoformat(),
                ),
            )

    def get_active_agents(self) -> List[dict]:
        """Get all active agents."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_registry WHERE is_active = 1"
            ).fetchall()
            return [dict(r) for r in rows]


# Global singletons
_duckdb: Optional[DuckDBManager] = None
_sqlite: Optional[SQLiteManager] = None


def get_duckdb() -> DuckDBManager:
    global _duckdb
    if _duckdb is None:
        _duckdb = DuckDBManager()
    return _duckdb


def get_sqlite() -> SQLiteManager:
    global _sqlite
    if _sqlite is None:
        _sqlite = SQLiteManager()
    return _sqlite
