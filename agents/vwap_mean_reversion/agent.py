"""VWAP Mean Reversion Strategy Agent.

Preferred regimes: RANGING
Logic:
  1. VWAP with 1, 2, 3 std dev bands
  2. Entry at +/- 2 std dev band
  3. Confirmation: RSI divergence OR volume climax
  4. Target: return to VWAP
  5. Stop: beyond +/- 3 std dev
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from agents.base import StrategyAgent
from core.types import Direction, FeatureVector, Regime, Signal


class VWAPMeanReversionAgent(StrategyAgent):
    agent_id = "vwap_mr"
    agent_name = "VWAP Mean Reversion"
    version = "1.0"
    preferred_regimes = [Regime.RANGING]
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self._params = {
            "entry_std": 2.0,            # Enter at this std dev from VWAP
            "stop_std": 3.0,             # Stop at this std dev
            "rsi_oversold": 30,          # RSI oversold for long
            "rsi_overbought": 70,        # RSI overbought for short
            "min_volume_ratio": 1.0,
            "require_rsi_extreme": False, # Require RSI < 30 / > 70
        }

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        f = features.features

        if not self.should_be_active(features.regime):
            return None

        vwap_std = f.get("vwap_std_position", 0)
        vwap_dist = f.get("vwap_dist_atr", 0)
        rsi = f.get("rsi_14", 50)
        atr = f.get("atr_14", 1.0)
        current_close = candles["close"].iloc[-1]

        if atr <= 0:
            return None

        direction = Direction.FLAT
        confidence = 0.5

        # ── Long signal: price at -2 std from VWAP ──────────────────
        if vwap_std <= -self._params["entry_std"]:
            direction = Direction.LONG
            confidence += 0.10

            if rsi < self._params["rsi_oversold"]:
                confidence += 0.15
            elif rsi < 40:
                confidence += 0.05

            # RSI divergence bonus
            if f.get("rsi_divergence", 0) > 0:
                confidence += 0.10

        # ── Short signal: price at +2 std from VWAP ─────────────────
        elif vwap_std >= self._params["entry_std"]:
            direction = Direction.SHORT
            confidence += 0.10

            if rsi > self._params["rsi_overbought"]:
                confidence += 0.15
            elif rsi > 60:
                confidence += 0.05

            if f.get("rsi_divergence", 0) < 0:
                confidence += 0.10

        else:
            return None

        # Volume confirmation
        vol = f.get("volume_ratio", 1.0)
        if vol > 1.5:
            confidence += 0.05
        elif vol < self._params["min_volume_ratio"]:
            confidence -= 0.05

        # Bollinger position confirmation
        boll_pos = f.get("boll_position", 0.5)
        if direction == Direction.LONG and boll_pos < 0.1:
            confidence += 0.05
        elif direction == Direction.SHORT and boll_pos > 0.9:
            confidence += 0.05

        # Stochastic confirmation
        stoch_k = f.get("stoch_k", 50)
        if direction == Direction.LONG and stoch_k < 20:
            confidence += 0.05
        elif direction == Direction.SHORT and stoch_k > 80:
            confidence += 0.05

        # Entry, stop, target
        vwap_to_price_dist = abs(vwap_dist) * atr
        stop_dist = abs(vwap_std) / self._params["entry_std"] * self._params["stop_std"] * atr * 0.5

        if direction == Direction.LONG:
            entry = current_close
            stop = entry - stop_dist
            target = entry + vwap_to_price_dist  # Target VWAP
        else:
            entry = current_close
            stop = entry + stop_dist
            target = entry - vwap_to_price_dist

        return self.create_signal(
            direction=direction,
            confidence=min(confidence, 0.95),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=(
                f"VWAP MR: std_pos={vwap_std:.2f}, RSI={rsi:.0f}, "
                f"vol_ratio={vol:.2f}, stoch_k={stoch_k:.0f}"
            ),
            features_used=["vwap_std_position", "vwap_dist_atr", "rsi_14",
                          "volume_ratio", "boll_position", "stoch_k"],
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
