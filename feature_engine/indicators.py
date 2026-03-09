"""Technical Indicator Computation Library.

Pure numpy/pandas implementations - no external TA library dependency.
Every indicator returns a pandas Series or DataFrame aligned to input index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Tuple


# ── Trend Indicators ─────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(period).mean()


def ema_slope(series: pd.Series, period: int, slope_lookback: int = 3) -> pd.Series:
    """EMA slope (rate of change over lookback bars)."""
    e = ema(series, period)
    return (e - e.shift(slope_lookback)) / slope_lookback


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD Line, Signal Line, Histogram."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (0-100 trend strength)."""
    tr = true_range(high, low, close)
    atr_val = ema(tr, period)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=close.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=close.index)

    plus_di = 100 * ema(plus_dm, period) / atr_val.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, period) / atr_val.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return ema(dx, period)


def linear_regression_slope(series: pd.Series, period: int = 20) -> pd.Series:
    """Slope of linear regression over rolling window."""
    def _slope(arr):
        if len(arr) < period or np.isnan(arr).any():
            return np.nan
        x = np.arange(len(arr))
        return np.polyfit(x, arr, 1)[0]
    return series.rolling(period).apply(_slope, raw=True)


# ── Mean Reversion Indicators ────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (0-100)."""
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rsi_divergence(close: pd.Series, rsi_series: pd.Series, lookback: int = 14) -> pd.Series:
    """Detect RSI divergence: price makes new high/low but RSI doesn't."""
    price_high = close.rolling(lookback).max() == close
    rsi_high = rsi_series.rolling(lookback).max() == rsi_series
    bearish_div = price_high & ~rsi_high

    price_low = close.rolling(lookback).min() == close
    rsi_low = rsi_series.rolling(lookback).min() == rsi_series
    bullish_div = price_low & ~rsi_low

    # 1 = bullish divergence, -1 = bearish divergence, 0 = none
    result = pd.Series(0.0, index=close.index)
    result[bullish_div] = 1.0
    result[bearish_div] = -1.0
    return result


def bollinger_bands(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands: upper, middle, lower."""
    middle = sma(close, period)
    std = close.rolling(period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return upper, middle, lower


def bollinger_position(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.Series:
    """Position within Bollinger Bands (0=lower, 1=upper)."""
    upper, _, lower = bollinger_bands(close, period, std_mult)
    band_width = (upper - lower).replace(0, np.nan)
    return (close - lower) / band_width


def bollinger_bandwidth(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.Series:
    """Bollinger bandwidth as volatility proxy."""
    upper, middle, lower = bollinger_bands(close, period, std_mult)
    return (upper - lower) / middle.replace(0, np.nan)


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """Stochastic %K and %D."""
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = sma(k, d_period)
    return k, d


def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    tp = (high + low + close) / 3
    ma = sma(tp, period)
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - ma) / (0.015 * mad).replace(0, np.nan)


# ── VWAP ─────────────────────────────────────────────────────────────────

def vwap_with_bands(high: pd.Series, low: pd.Series, close: pd.Series,
                    volume: pd.Series, session_groups: pd.Series,
                    std_bands: list = [1.0, 2.0, 3.0]) -> dict:
    """VWAP with standard deviation bands, reset per session.

    Args:
        session_groups: Series of date/session labels for VWAP reset.

    Returns:
        dict with 'vwap', 'upper_1', 'lower_1', 'upper_2', 'lower_2', etc.
    """
    tp = (high + low + close) / 3
    result = {
        "vwap": pd.Series(np.nan, index=close.index, dtype=float),
    }
    for b in std_bands:
        result[f"upper_{b}"] = pd.Series(np.nan, index=close.index, dtype=float)
        result[f"lower_{b}"] = pd.Series(np.nan, index=close.index, dtype=float)

    for _, group in pd.DataFrame({"tp": tp, "vol": volume, "grp": session_groups}).groupby("grp"):
        cum_vol = group["vol"].cumsum()
        cum_tp_vol = (group["tp"] * group["vol"]).cumsum()
        vwap_val = cum_tp_vol / cum_vol.replace(0, np.nan)
        result["vwap"].loc[group.index] = vwap_val

        # Standard deviation bands
        cum_sq = ((group["tp"] - vwap_val) ** 2 * group["vol"]).cumsum()
        std = np.sqrt(cum_sq / cum_vol.replace(0, np.nan))

        for b in std_bands:
            result[f"upper_{b}"].loc[group.index] = vwap_val + b * std
            result[f"lower_{b}"].loc[group.index] = vwap_val - b * std

    return result


# ── Volatility ───────────────────────────────────────────────────────────

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    tr = true_range(high, low, close)
    return ema(tr, period)


def atr_percentile(atr_series: pd.Series, lookback: int = 100) -> pd.Series:
    """ATR as percentile rank vs last N bars (0-100)."""
    return atr_series.rolling(lookback).apply(
        lambda x: (x[-1] >= x).sum() / len(x) * 100, raw=True
    )


def parkinson_volatility(high: pd.Series, low: pd.Series, period: int = 20) -> pd.Series:
    """Parkinson range-based volatility estimator."""
    log_hl = np.log(high / low.replace(0, np.nan))
    return np.sqrt((log_hl ** 2).rolling(period).mean() / (4 * np.log(2)))


def keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series,
                     ema_period: int = 20, atr_period: int = 14,
                     atr_mult: float = 1.5) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Keltner Channels: upper, middle, lower."""
    middle = ema(close, ema_period)
    atr_val = atr(high, low, close, atr_period)
    upper = middle + atr_mult * atr_val
    lower = middle - atr_mult * atr_val
    return upper, middle, lower


def is_squeeze(close: pd.Series, high: pd.Series, low: pd.Series,
               bb_period: int = 20, bb_std: float = 2.0,
               kc_ema: int = 20, kc_atr: int = 14, kc_mult: float = 1.5) -> pd.Series:
    """Bollinger Band squeeze: BB inside Keltner Channels."""
    bb_upper, _, bb_lower = bollinger_bands(close, bb_period, bb_std)
    kc_upper, _, kc_lower = keltner_channels(high, low, close, kc_ema, kc_atr, kc_mult)
    return (bb_lower > kc_lower) & (bb_upper < kc_upper)


# ── Volume ───────────────────────────────────────────────────────────────

def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Current volume / SMA(period) volume."""
    avg_vol = sma(volume, period)
    return volume / avg_vol.replace(0, np.nan)


def on_balance_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On Balance Volume."""
    direction = np.sign(close.diff())
    return (volume * direction).cumsum()


def obv_slope(close: pd.Series, volume: pd.Series, period: int = 10) -> pd.Series:
    """OBV slope over rolling window."""
    obv = on_balance_volume(close, volume)
    return linear_regression_slope(obv, period)


# ── Market Structure (SMC) ───────────────────────────────────────────────

def swing_highs(high: pd.Series, lookback: int = 5) -> pd.Series:
    """Detect swing highs using fractal pivot method.

    Returns: Series of swing high prices (NaN where not a swing high).
    """
    result = pd.Series(np.nan, index=high.index)
    arr = high.values

    for i in range(lookback, len(arr) - lookback):
        is_swing = True
        for j in range(1, lookback + 1):
            if arr[i] <= arr[i - j] or arr[i] <= arr[i + j]:
                is_swing = False
                break
        if is_swing:
            result.iloc[i] = arr[i]

    return result


def swing_lows(low: pd.Series, lookback: int = 5) -> pd.Series:
    """Detect swing lows using fractal pivot method."""
    result = pd.Series(np.nan, index=low.index)
    arr = low.values

    for i in range(lookback, len(arr) - lookback):
        is_swing = True
        for j in range(1, lookback + 1):
            if arr[i] >= arr[i - j] or arr[i] >= arr[i + j]:
                is_swing = False
                break
        if is_swing:
            result.iloc[i] = arr[i]

    return result


def detect_bos(close: pd.Series, swing_h: pd.Series, swing_l: pd.Series) -> pd.Series:
    """Detect Break of Structure.

    Returns: 1 for bullish BOS, -1 for bearish BOS, 0 for none.
    """
    result = pd.Series(0, index=close.index)

    last_sh = np.nan
    last_sl = np.nan

    for i in range(len(close)):
        if not np.isnan(swing_h.iloc[i]):
            last_sh = swing_h.iloc[i]
        if not np.isnan(swing_l.iloc[i]):
            last_sl = swing_l.iloc[i]

        if not np.isnan(last_sh) and close.iloc[i] > last_sh:
            result.iloc[i] = 1  # Bullish BOS
            last_sh = close.iloc[i]
        elif not np.isnan(last_sl) and close.iloc[i] < last_sl:
            result.iloc[i] = -1  # Bearish BOS
            last_sl = close.iloc[i]

    return result


def detect_choch(bos_series: pd.Series) -> pd.Series:
    """Detect Change of Character (first BOS in opposite direction).

    Returns: 1 for bullish CHoCH, -1 for bearish CHoCH, 0 for none.
    """
    result = pd.Series(0, index=bos_series.index)
    last_direction = 0

    for i in range(len(bos_series)):
        if bos_series.iloc[i] != 0:
            if last_direction != 0 and bos_series.iloc[i] != last_direction:
                result.iloc[i] = bos_series.iloc[i]
            last_direction = bos_series.iloc[i]

    return result


def detect_fvg(high: pd.Series, low: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Detect Fair Value Gaps (3-candle pattern).

    Returns:
        fvg_type: 1 for bullish FVG, -1 for bearish FVG, 0 for none
        fvg_top: top of the gap
        fvg_bottom: bottom of the gap
    """
    fvg_type = pd.Series(0, index=high.index)
    fvg_top = pd.Series(np.nan, index=high.index)
    fvg_bottom = pd.Series(np.nan, index=high.index)

    for i in range(2, len(high)):
        # Bullish FVG: candle 1 high < candle 3 low
        if low.iloc[i] > high.iloc[i - 2]:
            fvg_type.iloc[i] = 1
            fvg_top.iloc[i] = low.iloc[i]
            fvg_bottom.iloc[i] = high.iloc[i - 2]

        # Bearish FVG: candle 1 low > candle 3 high
        elif high.iloc[i] < low.iloc[i - 2]:
            fvg_type.iloc[i] = -1
            fvg_top.iloc[i] = low.iloc[i - 2]
            fvg_bottom.iloc[i] = high.iloc[i]

    return fvg_type, fvg_top, fvg_bottom


def detect_order_blocks(open_: pd.Series, high: pd.Series, low: pd.Series,
                        close: pd.Series, volume: pd.Series,
                        min_body_ratio: float = 0.5, min_vol_ratio: float = 1.3) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Detect order blocks: last opposing candle before impulsive move.

    Returns:
        ob_type: 1 for bullish OB, -1 for bearish OB, 0 for none
        ob_top: top of OB zone
        ob_bottom: bottom of OB zone
    """
    ob_type = pd.Series(0, index=close.index)
    ob_top = pd.Series(np.nan, index=close.index)
    ob_bottom = pd.Series(np.nan, index=close.index)

    body = (close - open_).abs()
    candle_range = (high - low).replace(0, np.nan)
    body_ratio = body / candle_range
    avg_vol = sma(volume, 20)
    vol_ratio = volume / avg_vol.replace(0, np.nan)

    for i in range(2, len(close)):
        # Bullish OB: bearish candle followed by strong bullish impulse
        is_impulse_up = (
            close.iloc[i] > open_.iloc[i]
            and body_ratio.iloc[i] > min_body_ratio
            and vol_ratio.iloc[i] > min_vol_ratio
            and close.iloc[i] > high.iloc[i - 1]
        )

        if is_impulse_up and close.iloc[i - 1] < open_.iloc[i - 1]:
            ob_type.iloc[i] = 1
            ob_top.iloc[i] = open_.iloc[i - 1]
            ob_bottom.iloc[i] = close.iloc[i - 1]

        # Bearish OB: bullish candle followed by strong bearish impulse
        is_impulse_down = (
            close.iloc[i] < open_.iloc[i]
            and body_ratio.iloc[i] > min_body_ratio
            and vol_ratio.iloc[i] > min_vol_ratio
            and close.iloc[i] < low.iloc[i - 1]
        )

        if is_impulse_down and close.iloc[i - 1] > open_.iloc[i - 1]:
            ob_type.iloc[i] = -1
            ob_top.iloc[i] = close.iloc[i - 1]
            ob_bottom.iloc[i] = open_.iloc[i - 1]

    return ob_type, ob_top, ob_bottom


def detect_liquidity_levels(high: pd.Series, low: pd.Series,
                            tolerance_pct: float = 0.001,
                            min_touches: int = 2,
                            lookback: int = 50) -> Tuple[pd.Series, pd.Series]:
    """Detect liquidity levels (equal highs/lows where stops accumulate).

    Returns:
        liq_above_distance: distance to nearest liquidity above (NaN if none)
        liq_below_distance: distance to nearest liquidity below (NaN if none)
    """
    liq_above = pd.Series(np.nan, index=high.index)
    liq_below = pd.Series(np.nan, index=low.index)

    for i in range(lookback, len(high)):
        window_highs = high.iloc[i - lookback:i]
        window_lows = low.iloc[i - lookback:i]
        current_price = (high.iloc[i] + low.iloc[i]) / 2

        # Find equal highs above
        for h_val in window_highs.dropna().unique():
            if h_val > current_price:
                touches = ((window_highs - h_val).abs() / h_val < tolerance_pct).sum()
                if touches >= min_touches:
                    dist = h_val - current_price
                    if np.isnan(liq_above.iloc[i]) or dist < liq_above.iloc[i]:
                        liq_above.iloc[i] = dist

        # Find equal lows below
        for l_val in window_lows.dropna().unique():
            if l_val < current_price:
                touches = ((window_lows - l_val).abs() / l_val < tolerance_pct).sum()
                if touches >= min_touches:
                    dist = current_price - l_val
                    if np.isnan(liq_below.iloc[i]) or dist < liq_below.iloc[i]:
                        liq_below.iloc[i] = dist

    return liq_above, liq_below
