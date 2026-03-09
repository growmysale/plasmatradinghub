"""Feature Engine - Transforms raw candles into feature vectors.

Computes ~80-100 features organized into 8 categories. Every feature
is available as both raw values and z-score normalized for ML consumption.

Architecture:
  raw candles -> indicator pipeline -> structure detection ->
  regime classification -> feature vector -> feature store + event bus
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from core.config import get_config
from core.types import FeatureVector, KillZone, MarketStructure, Regime
from feature_engine import indicators as ind

logger = logging.getLogger(__name__)


# Feature column names organized by category
FEATURE_COLUMNS = {
    # 1. Price Action (15 features)
    "price_action": [
        "returns_1bar", "returns_5bar", "returns_15bar", "returns_60bar",
        "range_atr_ratio", "body_ratio", "position_in_range", "gap",
        "higher_high", "higher_low", "new_swing_high", "new_swing_low",
        "bars_since_swing_high", "bars_since_swing_low",
        "dist_swing_high_atr",
    ],
    # 2. Trend Indicators (12 features)
    "trend": [
        "ema8_dist_atr", "ema8_slope", "ema20_dist_atr", "ema20_slope",
        "ema50_dist_atr", "ema50_slope", "ema_alignment",
        "macd_line", "macd_signal", "macd_hist",
        "adx_14", "linreg_slope_20",
    ],
    # 3. Mean Reversion (10 features)
    "mean_reversion": [
        "rsi_14", "rsi_7", "rsi_divergence",
        "boll_position", "boll_bandwidth",
        "vwap_dist_atr", "vwap_std_position",
        "stoch_k", "stoch_d", "cci_20",
    ],
    # 4. Volume / Order Flow (7 features)
    "volume": [
        "volume_ratio", "volume_trend",
        "delta", "cumulative_delta_trend",
        "obv_trend", "relative_volume_spike",
        "volume_ma_ratio",
    ],
    # 5. Volatility (8 features)
    "volatility": [
        "atr_14", "atr_percentile", "atr_expansion",
        "keltner_width", "boll_bw",
        "parkinson_vol", "is_squeeze",
        "atr_roc",
    ],
    # 6. Market Structure / SMC (13 features)
    "structure": [
        "market_structure", "last_bos_direction", "bars_since_bos",
        "last_choch_bars_ago", "is_in_fvg", "fvg_type",
        "nearest_ob_dist_atr", "nearest_ob_type",
        "liq_above_dist", "liq_below_dist",
        "displacement_mag", "premium_discount",
        "ob_fvg_confluence",
    ],
    # 7. Time / Calendar (10 features)
    "time": [
        "hour_sin", "hour_cos", "minute_sin", "minute_cos",
        "dow_sin", "dow_cos",
        "is_kill_zone", "kill_zone_id",
        "is_first_30min", "is_last_30min",
    ],
    # 8. Regime (5 features - populated by regime detector)
    "regime": [
        "regime_id", "regime_confidence",
        "regime_duration", "regime_transition_prob",
        "volatility_regime",
    ],
}


def get_all_feature_columns() -> List[str]:
    """Get flat list of all feature column names."""
    cols = []
    for cat_cols in FEATURE_COLUMNS.values():
        cols.extend(cat_cols)
    return cols


class FeatureEngine:
    """Computes ~80 features from raw candle data.

    Usage:
        engine = FeatureEngine()
        features_df = engine.compute(candles_df)
    """

    def __init__(self):
        self.config = get_config().features
        self._last_swing_high_bar = 0
        self._last_swing_low_bar = 0
        self._last_bos_bar = 0

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all features from OHLCV DataFrame.

        Args:
            df: DataFrame with columns: open, high, low, close, volume, ts

        Returns:
            DataFrame with all feature columns added.
        """
        if df.empty or len(df) < 60:
            logger.warning(f"Need at least 60 bars for features, got {len(df)}")
            return pd.DataFrame()

        result = pd.DataFrame(index=df.index)

        # Ensure ts column available
        if "ts" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df["ts"] = df.index

        o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

        # ── 1. Price Action ──────────────────────────────────────────
        result["returns_1bar"] = np.log(c / c.shift(1))
        result["returns_5bar"] = np.log(c / c.shift(5))
        result["returns_15bar"] = np.log(c / c.shift(15))
        result["returns_60bar"] = np.log(c / c.shift(60))

        atr_val = ind.atr(h, l, c, self.config.atr_period)
        atr_safe = atr_val.replace(0, np.nan)

        result["range_atr_ratio"] = (h - l) / atr_safe
        body = (c - o).abs()
        candle_range = (h - l).replace(0, np.nan)
        result["body_ratio"] = body / candle_range
        result["position_in_range"] = (c - l) / candle_range
        result["gap"] = o - c.shift(1)

        result["higher_high"] = (h > h.shift(1)).astype(float)
        result["higher_low"] = (l > l.shift(1)).astype(float)

        sh = ind.swing_highs(h, self.config.swing_lookback)
        sl = ind.swing_lows(l, self.config.swing_lookback)

        result["new_swing_high"] = (~sh.isna()).astype(float)
        result["new_swing_low"] = (~sl.isna()).astype(float)

        # Bars since last swing
        result["bars_since_swing_high"] = self._bars_since(sh)
        result["bars_since_swing_low"] = self._bars_since(sl)

        # Distance to most recent swing high in ATR units
        last_sh_price = sh.ffill()
        result["dist_swing_high_atr"] = (last_sh_price - c) / atr_safe

        # ── 2. Trend Indicators ──────────────────────────────────────
        for period in self.config.ema_periods:
            ema_val = ind.ema(c, period)
            result[f"ema{period}_dist_atr"] = (c - ema_val) / atr_safe
            result[f"ema{period}_slope"] = ind.ema_slope(c, period)

        ema8 = ind.ema(c, 8)
        ema20 = ind.ema(c, 20)
        ema50 = ind.ema(c, 50)

        # EMA alignment: 1.0 if 8>20>50 (bullish), -1.0 if reversed
        bullish_align = (ema8 > ema20) & (ema20 > ema50)
        bearish_align = (ema8 < ema20) & (ema20 < ema50)
        result["ema_alignment"] = pd.Series(0.0, index=c.index)
        result.loc[bullish_align, "ema_alignment"] = 1.0
        result.loc[bearish_align, "ema_alignment"] = -1.0

        macd_line, macd_signal, macd_hist = ind.macd(c)
        result["macd_line"] = macd_line / atr_safe
        result["macd_signal"] = macd_signal / atr_safe
        result["macd_hist"] = macd_hist / atr_safe

        result["adx_14"] = ind.adx(h, l, c, self.config.adx_period)
        result["linreg_slope_20"] = ind.linear_regression_slope(c, 20)

        # ── 3. Mean Reversion ────────────────────────────────────────
        rsi14 = ind.rsi(c, 14)
        rsi7 = ind.rsi(c, 7)
        result["rsi_14"] = rsi14
        result["rsi_7"] = rsi7
        result["rsi_divergence"] = ind.rsi_divergence(c, rsi14)

        result["boll_position"] = ind.bollinger_position(c)
        result["boll_bandwidth"] = ind.bollinger_bandwidth(c)

        # VWAP features
        if "ts" in df.columns:
            ts_series = pd.to_datetime(df["ts"])
            session_groups = ts_series.dt.date
        else:
            session_groups = pd.Series(range(len(c)), index=c.index) // 78

        vwap_data = ind.vwap_with_bands(h, l, c, v, session_groups)
        vwap_val = vwap_data["vwap"]
        result["vwap_dist_atr"] = (c - vwap_val) / atr_safe

        # VWAP std position
        upper2 = vwap_data.get("upper_2.0", vwap_val)
        lower2 = vwap_data.get("lower_2.0", vwap_val)
        vwap_range = (upper2 - lower2).replace(0, np.nan)
        result["vwap_std_position"] = (c - vwap_val) / (vwap_range / 4).replace(0, np.nan)

        stoch_k, stoch_d = ind.stochastic(h, l, c)
        result["stoch_k"] = stoch_k
        result["stoch_d"] = stoch_d
        result["cci_20"] = ind.cci(h, l, c, 20)

        # ── 4. Volume / Order Flow ───────────────────────────────────
        result["volume_ratio"] = ind.volume_ratio(v, 20)
        result["volume_trend"] = ind.linear_regression_slope(v, 10)
        result["delta"] = df.get("delta", v * 0)
        cum_delta = result["delta"].cumsum()
        result["cumulative_delta_trend"] = ind.linear_regression_slope(cum_delta, 10)
        result["obv_trend"] = ind.obv_slope(c, v)
        result["relative_volume_spike"] = (result["volume_ratio"] > 2.0).astype(float)
        result["volume_ma_ratio"] = v / ind.sma(v, 50).replace(0, np.nan)

        # ── 5. Volatility ────────────────────────────────────────────
        result["atr_14"] = atr_val
        result["atr_percentile"] = ind.atr_percentile(atr_val)
        atr50 = ind.atr(h, l, c, 50)
        result["atr_expansion"] = atr_val / atr50.replace(0, np.nan)

        kc_upper, kc_mid, kc_lower = ind.keltner_channels(h, l, c)
        result["keltner_width"] = (kc_upper - kc_lower) / kc_mid.replace(0, np.nan)
        result["boll_bw"] = result["boll_bandwidth"]
        result["parkinson_vol"] = ind.parkinson_volatility(h, l)
        result["is_squeeze"] = ind.is_squeeze(c, h, l).astype(float)
        result["atr_roc"] = atr_val.pct_change(5)

        # ── 6. Market Structure / SMC ────────────────────────────────
        bos = ind.detect_bos(c, sh, sl)
        choch = ind.detect_choch(bos)

        # Market structure state
        ms = pd.Series(0.0, index=c.index)
        ms[bos == 1] = 1.0
        ms[bos == -1] = -1.0
        result["market_structure"] = ms.replace(0, np.nan).ffill().fillna(0)

        result["last_bos_direction"] = bos.replace(0, np.nan).ffill().fillna(0)
        result["bars_since_bos"] = self._bars_since(bos.replace(0, np.nan))
        result["last_choch_bars_ago"] = self._bars_since(choch.replace(0, np.nan))

        fvg_type, fvg_top, fvg_bottom = ind.detect_fvg(h, l)
        result["is_in_fvg"] = self._is_price_in_zone(c, fvg_top, fvg_bottom, lookback=20)
        result["fvg_type"] = fvg_type.replace(0, np.nan).ffill().fillna(0)

        ob_type, ob_top, ob_bottom = ind.detect_order_blocks(o, h, l, c, v)
        result["nearest_ob_dist_atr"] = self._nearest_zone_distance(c, ob_top, ob_bottom, atr_safe, lookback=30)
        result["nearest_ob_type"] = ob_type.replace(0, np.nan).ffill().fillna(0)

        # Liquidity levels
        liq_above, liq_below = ind.detect_liquidity_levels(h, l)
        result["liq_above_dist"] = liq_above / atr_safe
        result["liq_below_dist"] = liq_below / atr_safe

        # Displacement magnitude
        result["displacement_mag"] = (c - c.shift(3)).abs() / atr_safe

        # Premium/Discount
        range_50 = (h.rolling(50).max() + l.rolling(50).min()) / 2
        range_span = (h.rolling(50).max() - l.rolling(50).min()).replace(0, np.nan)
        result["premium_discount"] = (c - range_50) / (range_span / 2)

        # OB + FVG confluence
        result["ob_fvg_confluence"] = (
            (result["is_in_fvg"] > 0) &
            (result["nearest_ob_dist_atr"].abs() < 1.0)
        ).astype(float)

        # ── 7. Time / Calendar ───────────────────────────────────────
        if "ts" in df.columns:
            ts = pd.to_datetime(df["ts"])
            hour = ts.dt.hour + ts.dt.minute / 60
            result["hour_sin"] = np.sin(2 * np.pi * hour / 24)
            result["hour_cos"] = np.cos(2 * np.pi * hour / 24)
            result["minute_sin"] = np.sin(2 * np.pi * ts.dt.minute / 60)
            result["minute_cos"] = np.cos(2 * np.pi * ts.dt.minute / 60)
            result["dow_sin"] = np.sin(2 * np.pi * ts.dt.dayofweek / 5)
            result["dow_cos"] = np.cos(2 * np.pi * ts.dt.dayofweek / 5)

            # Kill zones (ET times)
            result["is_kill_zone"] = (
                ((hour >= 2) & (hour < 5)) |      # London
                ((hour >= 8.5) & (hour < 11)) |    # NY AM
                ((hour >= 13) & (hour < 15))       # NY PM
            ).astype(float)

            result["kill_zone_id"] = pd.Series(0, index=c.index)
            result.loc[(hour >= 2) & (hour < 5), "kill_zone_id"] = 1       # London
            result.loc[(hour >= 8.5) & (hour < 11), "kill_zone_id"] = 2    # NY AM
            result.loc[(hour >= 13) & (hour < 15), "kill_zone_id"] = 3     # NY PM

            result["is_first_30min"] = ((hour >= 9.5) & (hour < 10)).astype(float)
            result["is_last_30min"] = ((hour >= 15.5) & (hour < 16)).astype(float)
        else:
            for col in FEATURE_COLUMNS["time"]:
                result[col] = 0.0

        # ── 8. Regime (placeholder - filled by regime detector) ──────
        result["regime_id"] = 0
        result["regime_confidence"] = 0.0
        result["regime_duration"] = 0
        result["regime_transition_prob"] = 0.0
        result["volatility_regime"] = result["atr_percentile"]

        # Fill NaN with 0 for ML consumption
        result = result.fillna(0)

        return result

    def compute_feature_vector(self, df: pd.DataFrame, idx: int = -1) -> FeatureVector:
        """Compute features and return a FeatureVector for a specific bar."""
        features_df = self.compute(df)
        if features_df.empty:
            return FeatureVector(symbol="MES", timeframe="5min", ts=datetime.now())

        row = features_df.iloc[idx]
        ts = df["ts"].iloc[idx] if "ts" in df.columns else datetime.now()

        fv = FeatureVector(
            symbol=df.get("symbol", pd.Series(["MES"])).iloc[0] if "symbol" in df.columns else "MES",
            timeframe=df.get("timeframe", pd.Series(["5min"])).iloc[0] if "timeframe" in df.columns else "5min",
            ts=ts,
            features=row.to_dict(),
            rsi_14=row.get("rsi_14", 50.0),
            atr_14=row.get("atr_14", 0.0),
            volume_ratio=row.get("volume_ratio", 1.0),
            vwap_distance_atr=row.get("vwap_dist_atr", 0.0),
            ema20_distance_atr=row.get("ema20_dist_atr", 0.0),
            is_kill_zone=bool(row.get("is_kill_zone", 0)),
        )

        # Set market structure
        ms_val = row.get("market_structure", 0)
        if ms_val > 0:
            fv.market_structure = MarketStructure.BULLISH
        elif ms_val < 0:
            fv.market_structure = MarketStructure.BEARISH
        else:
            fv.market_structure = MarketStructure.TRANSITIONING

        return fv

    @staticmethod
    def _bars_since(signal_series: pd.Series) -> pd.Series:
        """Count bars since last non-NaN signal."""
        result = pd.Series(999, index=signal_series.index, dtype=float)
        last_signal_idx = -999

        for i in range(len(signal_series)):
            if not pd.isna(signal_series.iloc[i]):
                last_signal_idx = i
            if last_signal_idx >= 0:
                result.iloc[i] = i - last_signal_idx

        return result

    @staticmethod
    def _is_price_in_zone(close: pd.Series, zone_top: pd.Series,
                          zone_bottom: pd.Series, lookback: int = 20) -> pd.Series:
        """Check if current price is inside any recent zone."""
        result = pd.Series(0.0, index=close.index)

        active_zones = []
        for i in range(len(close)):
            if not pd.isna(zone_top.iloc[i]) and not pd.isna(zone_bottom.iloc[i]):
                active_zones.append((zone_top.iloc[i], zone_bottom.iloc[i], i))

            # Remove old zones
            active_zones = [(t, b, idx) for t, b, idx in active_zones if i - idx < lookback]

            for top, bottom, _ in active_zones:
                mn, mx = min(top, bottom), max(top, bottom)
                if mn <= close.iloc[i] <= mx:
                    result.iloc[i] = 1.0
                    break

        return result

    @staticmethod
    def _nearest_zone_distance(close: pd.Series, zone_top: pd.Series,
                               zone_bottom: pd.Series, atr_val: pd.Series,
                               lookback: int = 30) -> pd.Series:
        """Distance to nearest zone in ATR units."""
        result = pd.Series(np.nan, index=close.index)

        active_zones = []
        for i in range(len(close)):
            if not pd.isna(zone_top.iloc[i]) and not pd.isna(zone_bottom.iloc[i]):
                mid = (zone_top.iloc[i] + zone_bottom.iloc[i]) / 2
                active_zones.append((mid, i))

            active_zones = [(m, idx) for m, idx in active_zones if i - idx < lookback]

            if active_zones and not pd.isna(atr_val.iloc[i]) and atr_val.iloc[i] > 0:
                distances = [abs(close.iloc[i] - m) / atr_val.iloc[i] for m, _ in active_zones]
                result.iloc[i] = min(distances)

        return result
