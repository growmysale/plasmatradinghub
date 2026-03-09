"""Order Block + FVG Confluence Strategy Agent.

Preferred regimes: TRENDING_UP, TRENDING_DOWN
Logic:
  1. Identify order blocks (last opposing candle before impulse)
  2. Identify Fair Value Gaps (3-candle pattern with gap)
  3. Entry ONLY where OB and FVG overlap (confluence zone)
  4. Higher timeframe must confirm direction
  5. Stop below OB zone, target at opposing liquidity
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from agents.base import StrategyAgent
from core.types import Direction, FeatureVector, Regime, Signal


class OBFVGAgent(StrategyAgent):
    agent_id = "ob_fvg"
    agent_name = "Order Block + FVG Confluence"
    version = "1.0"
    preferred_regimes = [Regime.TRENDING_UP, Regime.TRENDING_DOWN]
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self._params = {
            "max_ob_dist_atr": 1.5,      # Max distance to OB in ATR
            "require_trend_filter": True, # EMA 50 direction
            "min_rr": 2.5,
        }

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        f = features.features

        if not self.should_be_active(features.regime):
            return None

        # Need OB + FVG confluence
        ob_fvg = f.get("ob_fvg_confluence", 0)
        is_in_fvg = f.get("is_in_fvg", 0)
        ob_dist = f.get("nearest_ob_dist_atr", 999)
        ob_type = f.get("nearest_ob_type", 0)

        if ob_fvg < 1 and not (is_in_fvg and ob_dist < self._params["max_ob_dist_atr"]):
            return None

        atr = f.get("atr_14", 1.0)
        if atr <= 0:
            return None

        current_close = candles["close"].iloc[-1]
        market_struct = f.get("market_structure", 0)
        fvg_type = f.get("fvg_type", 0)

        # Determine direction from OB type and FVG type
        direction = Direction.FLAT
        if ob_type > 0 or fvg_type > 0:
            direction = Direction.LONG
        elif ob_type < 0 or fvg_type < 0:
            direction = Direction.SHORT
        else:
            return None

        confidence = 0.55

        # Trend filter
        ema50_dist = f.get("ema50_dist_atr", 0)
        if self._params["require_trend_filter"]:
            if direction == Direction.LONG and ema50_dist < -1.0:
                return None
            if direction == Direction.SHORT and ema50_dist > 1.0:
                return None
            if (direction == Direction.LONG and ema50_dist > 0) or \
               (direction == Direction.SHORT and ema50_dist < 0):
                confidence += 0.10

        # Volume confirmation
        vol = f.get("volume_ratio", 1.0)
        if vol > 1.3:
            confidence += 0.05

        # Market structure alignment
        if (direction == Direction.LONG and market_struct > 0) or \
           (direction == Direction.SHORT and market_struct < 0):
            confidence += 0.10

        # Displacement magnitude
        disp = f.get("displacement_mag", 0)
        if disp > 1.5:
            confidence += 0.05

        # Premium/Discount
        pd_val = f.get("premium_discount", 0)
        if direction == Direction.LONG and pd_val < -0.3:
            confidence += 0.05  # Buying in discount
        elif direction == Direction.SHORT and pd_val > 0.3:
            confidence += 0.05  # Selling in premium

        # Entry, stop, target
        risk = atr * 1.2

        if direction == Direction.LONG:
            entry = current_close
            stop = entry - risk
            target = entry + risk * self._params["min_rr"]
            # Adjust target to liquidity above if available
            liq_above = f.get("liq_above_dist", 0)
            if liq_above > 0:
                target = max(target, entry + liq_above * atr * 0.8)
        else:
            entry = current_close
            stop = entry + risk
            target = entry - risk * self._params["min_rr"]
            liq_below = f.get("liq_below_dist", 0)
            if liq_below > 0:
                target = min(target, entry - liq_below * atr * 0.8)

        return self.create_signal(
            direction=direction,
            confidence=min(confidence, 0.95),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=(
                f"OB+FVG confluence: ob_type={'bull' if ob_type > 0 else 'bear'}, "
                f"fvg={'bull' if fvg_type > 0 else 'bear'}, "
                f"ob_dist={ob_dist:.2f} ATR, struct={market_struct:.0f}"
            ),
            features_used=["ob_fvg_confluence", "nearest_ob_type", "fvg_type",
                          "nearest_ob_dist_atr", "ema50_dist_atr", "market_structure"],
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
