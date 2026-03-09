"""FRED Data Provider - Federal Reserve Economic Data.

Free, authoritative macroeconomic data for regime detection.
Used to feed macro features into the HMM regime detector.

Key series for trading:
- DFF: Federal Funds Rate (daily)
- T10Y2Y: 10Y-2Y Treasury Spread / yield curve (daily)
- VIXCLS: VIX volatility index (daily)
- CPIAUCSL: CPI inflation (monthly)
- UNRATE: Unemployment rate (monthly)

Usage:
    provider = FREDProvider()
    vix = provider.get_series("VIXCLS", start="2024-01-01")
    macro = provider.get_macro_snapshot()
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from fredapi import Fred
    HAS_FRED = True
except ImportError:
    HAS_FRED = False
    logger.info("fredapi not installed. Install with: pip install fredapi")


# Key FRED series for trading regime detection
MACRO_SERIES = {
    # Daily indicators
    "DFF": "Federal Funds Effective Rate",
    "T10Y2Y": "10Y-2Y Treasury Spread (Yield Curve)",
    "VIXCLS": "CBOE VIX Volatility Index",
    "DGS10": "10-Year Treasury Yield",
    "DGS2": "2-Year Treasury Yield",
    "BAMLH0A0HYM2": "High Yield OAS Spread",

    # Monthly indicators
    "CPIAUCSL": "CPI All Urban Consumers",
    "CPILFESL": "Core CPI (ex Food & Energy)",
    "UNRATE": "Unemployment Rate",
    "UMCSENT": "Consumer Sentiment (UMich)",

    # Quarterly indicators
    "GDPC1": "Real GDP",
}


class FREDProvider:
    """FRED macroeconomic data provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        self._client = None

        if not HAS_FRED:
            logger.warning("fredapi not installed")
            return

        if self.api_key:
            self._client = Fred(api_key=self.api_key)
            logger.info("FRED client initialized")
        else:
            logger.warning("FRED_API_KEY not set. Get free key at https://fred.stlouisfed.org/docs/api/fred/")

    @property
    def is_available(self) -> bool:
        return HAS_FRED and self._client is not None

    def get_series(
        self,
        series_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.Series:
        """Get a single FRED data series.

        Args:
            series_id: FRED series ID (e.g., "VIXCLS", "DFF")
            start: Start date (YYYY-MM-DD). Default: 1 year ago
            end: End date (YYYY-MM-DD). Default: today

        Returns:
            pandas Series with datetime index
        """
        if not self.is_available:
            raise RuntimeError("FRED not available")

        if start is None:
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        data = self._client.get_series(
            series_id,
            observation_start=start,
            observation_end=end,
        )

        logger.info(f"FRED {series_id}: {len(data)} observations from {start}")
        return data

    def get_macro_snapshot(self, lookback_days: int = 365) -> Dict[str, float]:
        """Get latest values for all key macro indicators.

        Returns dict of {series_id: latest_value}.
        Useful for regime detection features.
        """
        if not self.is_available:
            raise RuntimeError("FRED not available")

        start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        snapshot = {}

        for series_id, name in MACRO_SERIES.items():
            try:
                data = self._client.get_series(series_id, observation_start=start)
                if not data.empty:
                    latest = data.dropna().iloc[-1]
                    snapshot[series_id] = float(latest)
                    logger.debug(f"{name} ({series_id}): {latest}")
            except Exception as e:
                logger.warning(f"Failed to fetch {series_id}: {e}")

        logger.info(f"Macro snapshot: {len(snapshot)} indicators fetched")
        return snapshot

    def get_yield_curve_status(self) -> str:
        """Determine if yield curve is normal, flat, or inverted.

        Uses T10Y2Y spread:
        - > 0.5: Normal (economy healthy)
        - -0.25 to 0.5: Flat (uncertainty)
        - < -0.25: Inverted (recession signal)
        """
        if not self.is_available:
            return "unknown"

        try:
            spread = self.get_series("T10Y2Y")
            if spread.empty:
                return "unknown"

            latest = float(spread.dropna().iloc[-1])
            if latest > 0.5:
                return "normal"
            elif latest < -0.25:
                return "inverted"
            else:
                return "flat"
        except Exception:
            return "unknown"

    def get_vix_regime(self) -> str:
        """Classify VIX level into volatility regime.

        - < 15: Low vol (complacency)
        - 15-20: Normal
        - 20-30: Elevated (caution)
        - > 30: High vol (fear)
        """
        if not self.is_available:
            return "unknown"

        try:
            vix = self.get_series("VIXCLS")
            if vix.empty:
                return "unknown"

            latest = float(vix.dropna().iloc[-1])
            if latest < 15:
                return "low"
            elif latest < 20:
                return "normal"
            elif latest < 30:
                return "elevated"
            else:
                return "high"
        except Exception:
            return "unknown"
