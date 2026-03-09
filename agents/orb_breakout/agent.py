"""Opening Range Breakout Strategy Agent.

Preferred regimes: TRENDING_UP, TRENDING_DOWN, VOLATILE_EXPANSION
Logic:
  1. Define opening range = first 30 min of NY session (9:30-10:00 ET)
  2. Breakout above/below range with volume > 1.5x average
  3. Entry on breakout or retest of range boundary
  4. Stop: opposite side of range OR middle of range
  5. Target: 1.5x or 2x range width
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from agents.base import StrategyAgent
from core.types import Direction, FeatureVector, Regime, Signal


class ORBBreakoutAgent(StrategyAgent):
    agent_id = "orb"
    agent_name = "Opening Range Breakout"
    version = "1.0"
    preferred_regimes = [Regime.TRENDING_UP, Regime.TRENDING_DOWN, Regime.VOLATILE_EXPANSION]
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self._params = {
            "range_minutes": 30,         # Opening range period
            "target_multiplier": 1.5,    # Target = N x range width
            "stop_type": "opposite",     # "opposite" or "middle"
            "min_volume_ratio": 1.5,     # Volume spike on breakout
            "min_range_atr": 0.3,        # Min range width in ATR
            "max_range_atr": 2.0,        # Max range width in ATR
        }
        self._or_high = None
        self._or_low = None
        self._or_set = False
        self._current_day = None

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        f = features.features

        if not self.should_be_active(features.regime):
            return None

        if candles.empty or "ts" not in candles.columns:
            return None

        ts = pd.to_datetime(candles["ts"].iloc[-1])
        current_day = ts.date()

        # Reset on new day
        if current_day != self._current_day:
            self._current_day = current_day
            self._or_high = None
            self._or_low = None
            self._or_set = False

        # Build opening range during first 30 minutes
        hour_min = ts.hour * 60 + ts.minute
        or_start = 9 * 60 + 30   # 9:30 AM
        or_end = or_start + self._params["range_minutes"]

        if or_start <= hour_min < or_end:
            c_high = candles["high"].iloc[-1]
            c_low = candles["low"].iloc[-1]
            if self._or_high is None:
                self._or_high = c_high
                self._or_low = c_low
            else:
                self._or_high = max(self._or_high, c_high)
                self._or_low = min(self._or_low, c_low)
            return None

        if hour_min == or_end:
            self._or_set = True

        if not self._or_set or self._or_high is None or self._or_low is None:
            return None

        # Don't trade after 3 PM
        if hour_min > 15 * 60:
            return None

        atr = f.get("atr_14", 1.0)
        if atr <= 0:
            return None

        or_range = self._or_high - self._or_low
        range_atr = or_range / atr

        # Range size filter
        if range_atr < self._params["min_range_atr"] or range_atr > self._params["max_range_atr"]:
            return None

        current_close = candles["close"].iloc[-1]
        vol_ratio = f.get("volume_ratio", 1.0)

        direction = Direction.FLAT
        confidence = 0.50

        # Breakout above
        if current_close > self._or_high:
            direction = Direction.LONG
            confidence += 0.10

        # Breakout below
        elif current_close < self._or_low:
            direction = Direction.SHORT
            confidence += 0.10
        else:
            return None

        # Volume confirmation
        if vol_ratio >= self._params["min_volume_ratio"]:
            confidence += 0.15
        elif vol_ratio >= 1.2:
            confidence += 0.05
        else:
            confidence -= 0.10

        # EMA alignment
        ema_align = f.get("ema_alignment", 0)
        if (direction == Direction.LONG and ema_align == 1.0) or \
           (direction == Direction.SHORT and ema_align == -1.0):
            confidence += 0.10

        # ADX bonus
        adx = f.get("adx_14", 0)
        if adx > 25:
            confidence += 0.05

        # Entry, stop, target
        entry = current_close
        target_dist = or_range * self._params["target_multiplier"]

        if direction == Direction.LONG:
            if self._params["stop_type"] == "opposite":
                stop = self._or_low
            else:
                stop = (self._or_high + self._or_low) / 2
            target = entry + target_dist
        else:
            if self._params["stop_type"] == "opposite":
                stop = self._or_high
            else:
                stop = (self._or_high + self._or_low) / 2
            target = entry - target_dist

        return self.create_signal(
            direction=direction,
            confidence=min(confidence, 0.95),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=(
                f"ORB {'breakout above' if direction == Direction.LONG else 'breakdown below'} "
                f"range [{self._or_low:.2f}-{self._or_high:.2f}], "
                f"range={or_range:.2f} ({range_atr:.1f} ATR), vol_ratio={vol_ratio:.2f}"
            ),
            features_used=["volume_ratio", "ema_alignment", "adx_14"],
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
