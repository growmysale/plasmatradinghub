"""Momentum Trend Following Strategy Agent.

Preferred regimes: TRENDING_UP, TRENDING_DOWN
Logic:
  1. EMA 8 > EMA 20 > EMA 50 for longs (reverse for shorts)
  2. ADX > 25 confirms trend strength
  3. Entry on pullback to EMA 20 with decisive candle
  4. Stop below EMA 50 or recent swing low
  5. Trail stop using EMA 20 once in profit
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from agents.base import StrategyAgent
from core.types import Direction, FeatureVector, Regime, Signal


class MomentumAgent(StrategyAgent):
    agent_id = "momentum"
    agent_name = "Momentum Trend Follower"
    version = "1.0"
    preferred_regimes = [Regime.TRENDING_UP, Regime.TRENDING_DOWN]
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self._params = {
            "min_adx": 25,
            "pullback_ema": 20,          # Entry near EMA 20
            "pullback_tolerance_atr": 0.5,
            "stop_ema": 50,              # Stop at EMA 50
            "min_rr": 2.0,
        }

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        f = features.features

        if not self.should_be_active(features.regime):
            return None

        ema_align = f.get("ema_alignment", 0)
        adx_val = f.get("adx_14", 0)
        atr = f.get("atr_14", 1.0)

        if atr <= 0:
            return None

        # Need EMA alignment
        if ema_align == 0:
            return None

        # Need ADX strength
        if adx_val < self._params["min_adx"]:
            return None

        # Check pullback to EMA 20
        ema20_dist = f.get("ema20_dist_atr", 0)

        direction = Direction.FLAT
        confidence = 0.50

        if ema_align == 1.0:  # Bullish alignment
            # Price pulling back to EMA 20 (small positive or slightly negative dist)
            if -self._params["pullback_tolerance_atr"] <= ema20_dist <= self._params["pullback_tolerance_atr"]:
                direction = Direction.LONG
                confidence += 0.15
            elif 0 < ema20_dist < 1.0:
                direction = Direction.LONG
                confidence += 0.05
            else:
                return None

        elif ema_align == -1.0:  # Bearish alignment
            if -self._params["pullback_tolerance_atr"] <= ema20_dist <= self._params["pullback_tolerance_atr"]:
                direction = Direction.SHORT
                confidence += 0.15
            elif -1.0 < ema20_dist < 0:
                direction = Direction.SHORT
                confidence += 0.05
            else:
                return None

        # ADX strength bonus
        if adx_val > 35:
            confidence += 0.10
        elif adx_val > 30:
            confidence += 0.05

        # MACD histogram confirmation
        macd_hist = f.get("macd_hist", 0)
        if (direction == Direction.LONG and macd_hist > 0) or \
           (direction == Direction.SHORT and macd_hist < 0):
            confidence += 0.05

        # Candle body ratio (decisive)
        body = f.get("body_ratio", 0)
        if body > 0.6:
            confidence += 0.05

        # Volume
        vol = f.get("volume_ratio", 1.0)
        if vol > 1.3:
            confidence += 0.05

        # Linear regression slope confirmation
        lr_slope = f.get("linreg_slope_20", 0)
        if (direction == Direction.LONG and lr_slope > 0) or \
           (direction == Direction.SHORT and lr_slope < 0):
            confidence += 0.05

        current_close = candles["close"].iloc[-1]
        ema50_dist = abs(f.get("ema50_dist_atr", 0)) * atr

        if direction == Direction.LONG:
            entry = current_close
            stop = entry - max(ema50_dist, atr * 1.0)
            risk = entry - stop
            target = entry + risk * self._params["min_rr"]
        else:
            entry = current_close
            stop = entry + max(ema50_dist, atr * 1.0)
            risk = stop - entry
            target = entry - risk * self._params["min_rr"]

        return self.create_signal(
            direction=direction,
            confidence=min(confidence, 0.95),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=(
                f"Momentum: EMA align={'bull' if ema_align > 0 else 'bear'}, "
                f"ADX={adx_val:.0f}, pullback ema20_dist={ema20_dist:.2f}, "
                f"MACD hist={macd_hist:.4f}"
            ),
            features_used=["ema_alignment", "adx_14", "ema20_dist_atr",
                          "macd_hist", "body_ratio", "linreg_slope_20"],
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
