"""Databento Data Provider - Institutional-grade MES/ES futures data.

Databento is a CME-certified vendor providing tick, minute, and OHLCV data.
Dataset: GLBX.MDP3 (CME Globex)

Pricing:
- $125 free credits on signup (enough for months of backtesting dev)
- Pay-as-you-go: ~$2.17 for 5 days of ES trades
- Standard plan: $179/month (live streaming + 7yr history)

Usage:
    provider = DatabentoProvider()
    df = provider.get_historical_bars("MES.FUT", "2024-01-01", "2024-06-30")
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Databento SDK is optional - install with: pip install databento
try:
    import databento as db
    HAS_DATABENTO = True
except ImportError:
    HAS_DATABENTO = False
    logger.info("databento not installed. Install with: pip install databento")


class DatabentoProvider:
    """Databento historical and live MES/ES data provider."""

    DATASET = "GLBX.MDP3"  # CME Globex

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DATABENTO_API_KEY", "")
        self._client = None

        if not HAS_DATABENTO:
            logger.warning("databento SDK not installed")
            return

        if self.api_key:
            self._client = db.Historical(key=self.api_key)
            logger.info("Databento client initialized")
        else:
            logger.warning("DATABENTO_API_KEY not set")

    @property
    def is_available(self) -> bool:
        return HAS_DATABENTO and self._client is not None

    def estimate_cost(
        self,
        symbol: str = "MES.FUT",
        schema: str = "ohlcv-1m",
        start: str = "2024-01-01",
        end: str = "2024-06-30",
    ) -> float:
        """Estimate the cost of a historical data request before downloading.

        Returns cost in USD.
        """
        if not self.is_available:
            raise RuntimeError("Databento not available")

        cost = self._client.metadata.get_cost(
            dataset=self.DATASET,
            symbols=[symbol],
            schema=schema,
            start=start,
            end=end,
        )
        logger.info(f"Estimated cost for {symbol} {schema} {start}->{end}: ${cost:.4f}")
        return cost

    def get_historical_bars(
        self,
        symbol: str = "MES.FUT",
        start: str = "2024-01-01",
        end: str = "2024-06-30",
        schema: str = "ohlcv-1m",
    ) -> pd.DataFrame:
        """Download historical OHLCV bars from Databento.

        Args:
            symbol: Futures symbol (e.g., "MES.FUT" for continuous front month)
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            schema: Data schema - "ohlcv-1m", "ohlcv-1h", "ohlcv-1d", "trades"

        Returns:
            DataFrame with columns: ts, open, high, low, close, volume
        """
        if not self.is_available:
            raise RuntimeError("Databento not available")

        logger.info(f"Downloading {symbol} {schema} from {start} to {end}")

        data = self._client.timeseries.get_range(
            dataset=self.DATASET,
            symbols=[symbol],
            schema=schema,
            start=start,
            end=end,
        )

        df = data.to_df()

        if df.empty:
            logger.warning("No data returned from Databento")
            return pd.DataFrame()

        # Normalize column names
        df = df.reset_index()
        rename_map = {
            "ts_event": "ts",
        }
        df = df.rename(columns=rename_map)

        # Ensure standard OHLCV columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                logger.warning(f"Missing column: {col}")

        logger.info(f"Downloaded {len(df)} bars from Databento")
        return df

    def get_trades(
        self,
        symbol: str = "MES.FUT",
        start: str = "2024-01-01",
        end: str = "2024-01-02",
    ) -> pd.DataFrame:
        """Download tick-level trade data.

        Warning: Tick data is much larger and more expensive than bars.
        """
        return self.get_historical_bars(symbol, start, end, schema="trades")
