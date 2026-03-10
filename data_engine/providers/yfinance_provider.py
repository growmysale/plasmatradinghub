"""Yahoo Finance Data Provider for PropEdge.

Downloads free historical ES/MES futures data from Yahoo Finance.
ES=F (E-mini S&P 500) tracks MES 1:1 in price — same price action,
just 10x the contract size.

Data limits (Yahoo Finance free tier):
  - 5-min bars:  last 60 trading days (~4,680 bars)
  - 15-min bars: last 60 trading days
  - 1-hour bars: last 730 days (~14,000 bars)
  - Daily bars:  unlimited history

Usage:
    provider = YFinanceProvider()
    count = provider.download_and_store(timeframe="5min")
    print(f"Downloaded {count} candles")
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from core.types import Candle
from data_engine.candle_store import CandleStore

logger = logging.getLogger(__name__)

# Yahoo Finance ticker for E-mini S&P 500 futures (continuous front month)
ES_TICKER = "ES=F"

# Map our timeframes to yfinance intervals
TIMEFRAME_MAP = {
    "1min": {"interval": "1m", "max_days": 7},
    "5min": {"interval": "5m", "max_days": 60},
    "15min": {"interval": "15m", "max_days": 60},
    "30min": {"interval": "30m", "max_days": 60},
    "1hour": {"interval": "60m", "max_days": 730},
    "1day": {"interval": "1d", "max_days": 3650},
}


class YFinanceProvider:
    """Downloads ES/MES futures data from Yahoo Finance (free)."""

    def __init__(self, symbol: str = "MES"):
        self.symbol = symbol
        self._store = CandleStore()

    def download(
        self,
        timeframe: str = "5min",
        days: Optional[int] = None,
    ) -> List[Candle]:
        """Download historical data from Yahoo Finance.

        Args:
            timeframe: One of "1min", "5min", "15min", "30min", "1hour", "1day"
            days: Number of days to download (capped by Yahoo's limits)

        Returns:
            List of Candle objects
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.error(
                "yfinance not installed. Run: pip install yfinance"
            )
            return []

        tf_config = TIMEFRAME_MAP.get(timeframe)
        if not tf_config:
            logger.error(f"Unsupported timeframe: {timeframe}")
            return []

        max_days = tf_config["max_days"]
        interval = tf_config["interval"]

        if days is None:
            days = max_days
        days = min(days, max_days)

        logger.info(
            f"Downloading {days} days of {timeframe} ES futures data "
            f"from Yahoo Finance..."
        )

        try:
            end = datetime.now()
            start = end - timedelta(days=days)

            ticker = yf.Ticker(ES_TICKER)
            df = ticker.history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
            )

            if df.empty:
                logger.warning("No data returned from Yahoo Finance")
                return []

            candles = self._dataframe_to_candles(df, timeframe)
            logger.info(
                f"Downloaded {len(candles)} {timeframe} candles "
                f"({df.index[0].date()} to {df.index[-1].date()})"
            )
            return candles

        except Exception as e:
            logger.error(f"Yahoo Finance download error: {e}")
            return []

    def download_and_store(
        self,
        timeframe: str = "5min",
        days: Optional[int] = None,
    ) -> int:
        """Download and store candles in DuckDB.

        Returns number of candles stored.
        """
        candles = self.download(timeframe=timeframe, days=days)
        if not candles:
            return 0

        # Insert in batches of 1000
        batch_size = 1000
        for i in range(0, len(candles), batch_size):
            batch = candles[i:i + batch_size]
            self._store.insert_candles(batch)

        logger.info(f"Stored {len(candles)} {timeframe} candles in DuckDB")
        return len(candles)

    def download_multi_timeframe(self) -> dict:
        """Download all available timeframes for comprehensive analysis.

        Returns dict of {timeframe: count} for candles stored.
        """
        results = {}

        # 5-min: primary trading timeframe (60 days)
        results["5min"] = self.download_and_store("5min")

        # 1-hour: for regime detection and swing structure (2 years)
        results["1hour"] = self.download_and_store("1hour")

        # Daily: for long-term context (10 years)
        results["1day"] = self.download_and_store("1day")

        total = sum(results.values())
        logger.info(
            f"Multi-timeframe download complete: "
            f"{total} total candles across {len(results)} timeframes"
        )
        return results

    def _dataframe_to_candles(
        self,
        df: pd.DataFrame,
        timeframe: str,
    ) -> List[Candle]:
        """Convert yfinance DataFrame to list of Candle objects."""
        candles = []

        for ts, row in df.iterrows():
            # Skip rows with NaN prices
            if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
                continue

            # Convert to naive datetime (yfinance returns timezone-aware)
            if hasattr(ts, "tz") and ts.tz is not None:
                ts = ts.tz_localize(None)

            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            v = float(row.get("Volume", 0))

            # Round to MES tick boundaries (0.25)
            o = round(o * 4) / 4
            h = round(h * 4) / 4
            l = round(l * 4) / 4
            c = round(c * 4) / 4

            # Estimate buy/sell volume split (no real order flow from Yahoo)
            # Use price direction as a proxy
            if c >= o:
                buy_pct = 0.55 + np.random.uniform(-0.05, 0.05)
            else:
                buy_pct = 0.45 + np.random.uniform(-0.05, 0.05)
            buy_pct = max(0.3, min(0.7, buy_pct))

            buy_vol = v * buy_pct
            sell_vol = v * (1 - buy_pct)

            candles.append(Candle(
                symbol=self.symbol,
                timeframe=timeframe,
                ts=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                vwap=round((o + h + l + c) / 4 * 4) / 4,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                delta=buy_vol - sell_vol,
            ))

        return candles

    def get_data_status(self) -> dict:
        """Get status of currently stored data."""
        status = {}
        for tf in ["5min", "15min", "1hour", "1day"]:
            count = self._store.get_candle_count(
                symbol=self.symbol, timeframe=tf
            )
            date_range = self._store.get_date_range(
                symbol=self.symbol, timeframe=tf
            )
            status[tf] = {
                "count": count,
                "start": (
                    date_range[0].isoformat()
                    if date_range[0] else None
                ),
                "end": (
                    date_range[1].isoformat()
                    if date_range[1] else None
                ),
            }
        return status
