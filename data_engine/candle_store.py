"""Candle data storage and retrieval.

Handles loading candles from CSV/API, storing in DuckDB, and
providing efficient access for feature computation and backtesting.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from core.config import get_config
from core.types import Candle
from data_engine.database import get_duckdb

logger = logging.getLogger(__name__)


class CandleStore:
    """Manages OHLCV candle data in DuckDB."""

    def __init__(self):
        self.db = get_duckdb()

    def insert_candles(self, candles: List[Candle]):
        """Insert candles into DuckDB."""
        if not candles:
            return

        rows = [
            (c.symbol, c.timeframe, c.ts, c.open, c.high, c.low, c.close,
             c.volume, c.tick_count, c.vwap, c.buy_volume, c.sell_volume, c.delta)
            for c in candles
        ]

        self.db.conn.executemany(
            """INSERT OR REPLACE INTO candles
               (symbol, timeframe, ts, open, high, low, close, volume,
                tick_count, vwap, buy_volume, sell_volume, delta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

        logger.info(f"Inserted {len(candles)} candles for {candles[0].symbol}/{candles[0].timeframe}")

    def get_candles(
        self,
        symbol: str = "MES",
        timeframe: str = "5min",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 10000,
    ) -> pd.DataFrame:
        """Fetch candles as DataFrame."""
        query = "SELECT * FROM candles WHERE symbol = ? AND timeframe = ?"
        params = [symbol, timeframe]

        if start:
            query += " AND ts >= ?"
            params.append(start)
        if end:
            query += " AND ts <= ?"
            params.append(end)

        query += " ORDER BY ts ASC"
        if limit > 0:
            query += f" LIMIT {limit}"

        try:
            df = self.db.fetchdf(query, params)
            if not df.empty and "ts" in df.columns:
                df["ts"] = pd.to_datetime(df["ts"])
                df = df.set_index("ts", drop=False)
            return df
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return pd.DataFrame()

    def get_latest_candle(self, symbol: str = "MES", timeframe: str = "5min") -> Optional[Candle]:
        """Get the most recent candle."""
        rows = self.db.fetchall(
            "SELECT * FROM candles WHERE symbol = ? AND timeframe = ? ORDER BY ts DESC LIMIT 1",
            [symbol, timeframe],
        )
        if rows:
            r = rows[0]
            return Candle(
                symbol=r[0], timeframe=r[1], ts=r[2],
                open=r[3], high=r[4], low=r[5], close=r[6],
                volume=r[7] or 0, tick_count=r[8] or 0,
                vwap=r[9] or 0, buy_volume=r[10] or 0,
                sell_volume=r[11] or 0, delta=r[12] or 0,
            )
        return None

    def get_candle_count(self, symbol: str = "MES", timeframe: str = "5min") -> int:
        """Count candles in store."""
        rows = self.db.fetchall(
            "SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        )
        return rows[0][0] if rows else 0

    def get_date_range(self, symbol: str = "MES", timeframe: str = "5min") -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get first and last timestamp in store."""
        rows = self.db.fetchall(
            "SELECT MIN(ts), MAX(ts) FROM candles WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        )
        if rows and rows[0][0]:
            return rows[0][0], rows[0][1]
        return None, None

    def load_csv(self, csv_path: str, symbol: str = "MES", timeframe: str = "5min"):
        """Load candles from a CSV file.

        Expected columns: timestamp/datetime/date, open, high, low, close, volume
        """
        path = Path(csv_path)
        if not path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            return

        df = pd.read_csv(csv_path)

        # Try to find the timestamp column
        ts_col = None
        for col in ["timestamp", "datetime", "date", "ts", "time", "Date", "Datetime"]:
            if col in df.columns:
                ts_col = col
                break

        if ts_col is None:
            ts_col = df.columns[0]

        df[ts_col] = pd.to_datetime(df[ts_col])

        # Map columns
        col_map = {}
        for target, candidates in {
            "open": ["open", "Open", "o"],
            "high": ["high", "High", "h"],
            "low": ["low", "Low", "l"],
            "close": ["close", "Close", "c"],
            "volume": ["volume", "Volume", "vol", "Vol", "v"],
        }.items():
            for c in candidates:
                if c in df.columns:
                    col_map[target] = c
                    break

        candles = []
        for _, row in df.iterrows():
            candles.append(Candle(
                symbol=symbol,
                timeframe=timeframe,
                ts=row[ts_col],
                open=float(row[col_map.get("open", "open")]),
                high=float(row[col_map.get("high", "high")]),
                low=float(row[col_map.get("low", "low")]),
                close=float(row[col_map.get("close", "close")]),
                volume=float(row.get(col_map.get("volume", "volume"), 0)),
            ))

        self.insert_candles(candles)
        logger.info(f"Loaded {len(candles)} candles from {csv_path}")


def generate_sample_data(days: int = 90, start_price: float = 5600.0) -> int:
    """Generate realistic MES 5-minute candle data for testing.

    Returns number of candles generated.
    """
    store = CandleStore()
    candles = []
    price = start_price
    dt = datetime(2025, 10, 1, 9, 30)

    for day in range(days):
        while dt.weekday() >= 5:
            dt += timedelta(days=1)

        daily_vol = np.random.uniform(0.003, 0.015)
        daily_drift = np.random.normal(0, 0.001)

        for bar in range(78):  # 9:30 AM - 4:00 PM = 78 five-min bars
            bar_time = dt + timedelta(minutes=bar * 5)
            hour = bar_time.hour + bar_time.minute / 60

            # Time-based volatility
            time_vol_mult = 1.0
            if hour < 10.5:
                time_vol_mult = 1.5
            elif hour > 15:
                time_vol_mult = 1.3
            elif 12 <= hour <= 13:
                time_vol_mult = 0.6

            bar_vol = daily_vol / np.sqrt(78) * time_vol_mult
            returns = np.random.normal(daily_drift / 78, bar_vol)

            open_price = price
            close_price = price * (1 + returns)

            wick_factor = abs(returns) * np.random.uniform(0.5, 2.0)
            high = max(open_price, close_price) + abs(np.random.normal(0, price * wick_factor * 0.5))
            low = min(open_price, close_price) - abs(np.random.normal(0, price * wick_factor * 0.5))

            # MES tick boundaries (0.25)
            open_price = round(open_price * 4) / 4
            high = round(high * 4) / 4
            low = round(low * 4) / 4
            close_price = round(close_price * 4) / 4

            base_volume = np.random.randint(500, 3000)
            volume = int(base_volume * time_vol_mult)
            buy_vol = volume * np.random.uniform(0.35, 0.65)
            sell_vol = volume - buy_vol

            candles.append(Candle(
                symbol="MES",
                timeframe="5min",
                ts=bar_time,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=volume,
                vwap=round((open_price + high + low + close_price) / 4 * 4) / 4,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                delta=buy_vol - sell_vol,
            ))

            price = close_price

        dt += timedelta(days=1)

    store.insert_candles(candles)
    logger.info(f"Generated {len(candles)} sample candles ({days} trading days)")
    return len(candles)
