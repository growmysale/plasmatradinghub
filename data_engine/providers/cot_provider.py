"""CFTC Commitment of Traders (COT) Data Provider.

Free weekly positioning data showing how institutional traders
are positioned in ES/MES futures.

Released every Friday (data from Tuesday).
Used as a contrarian sentiment indicator for regime detection.

Usage:
    provider = COTProvider()
    data = provider.get_es_positioning()
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from cot_reports import cot_reports
    HAS_COT = True
except ImportError:
    HAS_COT = False
    logger.info("cot_reports not installed. Install with: pip install cot_reports")


class COTProvider:
    """CFTC COT data provider for ES/MES positioning data."""

    def __init__(self):
        if not HAS_COT:
            logger.warning("cot_reports not installed")

    @property
    def is_available(self) -> bool:
        return HAS_COT

    def get_traders_in_financial_futures(self) -> pd.DataFrame:
        """Get full Traders in Financial Futures report.

        This is the most relevant report for ES/MES containing:
        - Dealer/Intermediary positions
        - Asset Manager/Institutional positions
        - Leveraged Funds positions
        - Other Reportables
        """
        if not self.is_available:
            raise RuntimeError("cot_reports not available")

        df = cot_reports(report_type="traders_in_financial_futures_fut")
        return df

    def get_es_positioning(self) -> Dict:
        """Get current E-mini S&P 500 positioning data.

        Returns dict with:
        - leveraged_long: Leveraged funds net long contracts
        - leveraged_short: Leveraged funds net short contracts
        - leveraged_net: Net positioning
        - asset_mgr_net: Asset manager net positioning
        - dealer_net: Dealer/intermediary net positioning
        - sentiment: "bullish" / "bearish" / "neutral"
        """
        if not self.is_available:
            raise RuntimeError("cot_reports not available")

        try:
            df = self.get_traders_in_financial_futures()

            # Filter for E-mini S&P 500
            es_mask = df["Market_and_Exchange_Names"].str.contains("E-MINI S&P", case=False, na=False)
            es_data = df[es_mask]

            if es_data.empty:
                logger.warning("No E-mini S&P 500 data found in COT report")
                return {"sentiment": "unknown"}

            # Get the latest report
            latest = es_data.sort_values("As_of_Date_In_Form_YYMMDD", ascending=False).iloc[0]

            # Extract positioning
            lev_long = float(latest.get("Lev_Money_Positions_Long_All", 0))
            lev_short = float(latest.get("Lev_Money_Positions_Short_All", 0))
            lev_net = lev_long - lev_short

            asset_long = float(latest.get("Asset_Mgr_Positions_Long_All", 0))
            asset_short = float(latest.get("Asset_Mgr_Positions_Short_All", 0))
            asset_net = asset_long - asset_short

            dealer_long = float(latest.get("Dealer_Positions_Long_All", 0))
            dealer_short = float(latest.get("Dealer_Positions_Short_All", 0))
            dealer_net = dealer_long - dealer_short

            # Simple sentiment classification based on leveraged funds
            if lev_net > 0:
                sentiment = "bullish"
            elif lev_net < 0:
                sentiment = "bearish"
            else:
                sentiment = "neutral"

            return {
                "leveraged_long": lev_long,
                "leveraged_short": lev_short,
                "leveraged_net": lev_net,
                "asset_mgr_net": asset_net,
                "dealer_net": dealer_net,
                "sentiment": sentiment,
                "report_date": str(latest.get("As_of_Date_In_Form_YYMMDD", "")),
            }

        except Exception as e:
            logger.error(f"Failed to get ES positioning: {e}")
            return {"sentiment": "unknown", "error": str(e)}
