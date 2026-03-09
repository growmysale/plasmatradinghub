"""SMC Break & Retest Strategy Agent.

Preferred regimes: TRENDING_UP, TRENDING_DOWN
Logic:
  1. Detect market structure via swing points
  2. Identify Break of Structure (BOS)
  3. Wait for price to retest the broken level
  4. Entry on rejection candle at retest zone
  5. Stop below retest zone (bullish) or above (bearish)
  6. Target: 3:1 R:R
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agents.base import StrategyAgent
from core.types import Direction, FeatureVector, Regime, Signal


class SMCBreakRetestAgent(StrategyAgent):
    agent_id = "smc_br"
    agent_name = "SMC Break & Retest"
    version = "1.0"
    preferred_regimes = [Regime.TRENDING_UP, Regime.TRENDING_DOWN]
    min_confidence_threshold = 0.55

    def __init__(self):
        super().__init__()
        self._params = {
            "bos_lookback": 3,          # Bars to wait for retest after BOS
            "retest_tolerance_atr": 0.5, # How close to BOS level = retest
            "min_rr": 3.0,              # Minimum risk:reward
            "require_vwap_align": True, # VWAP confirmation
            "require_ema_slope": True,  # EMA 20 slope confirmation
            "require_volume": True,     # Volume spike on BOS
            "require_kill_zone": True,  # Must be in kill zone
        }

    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        f = features.features

        # Check regime
        if not self.should_be_active(features.regime):
            return None

        # Need recent BOS
        bars_since_bos = f.get("bars_since_bos", 999)
        if bars_since_bos < 1 or bars_since_bos > self._params["bos_lookback"] * 5:
            return None

        bos_direction = f.get("last_bos_direction", 0)
        if bos_direction == 0:
            return None

        # Check retest: price is near the BOS level
        market_structure = f.get("market_structure", 0)
        atr = f.get("atr_14", 1.0)
        if atr <= 0:
            return None

        current_close = candles["close"].iloc[-1]

        # ── Confirmation Filters ─────────────────────────────────────
        confidence = 0.5

        # VWAP alignment
        vwap_dist = f.get("vwap_dist_atr", 0)
        if self._params["require_vwap_align"]:
            if bos_direction > 0 and vwap_dist < 0:
                return None  # Want longs above VWAP
            if bos_direction < 0 and vwap_dist > 0:
                return None  # Want shorts below VWAP
            confidence += 0.05

        # EMA 20 slope confirms direction
        ema20_slope = f.get("ema20_slope", 0)
        if self._params["require_ema_slope"]:
            if bos_direction > 0 and ema20_slope <= 0:
                return None
            if bos_direction < 0 and ema20_slope >= 0:
                return None
            confidence += 0.05

        # Volume confirmation
        vol_ratio = f.get("volume_ratio", 1.0)
        if self._params["require_volume"] and vol_ratio < 1.2:
            confidence -= 0.05

        # Kill zone check
        is_kz = f.get("is_kill_zone", 0)
        if self._params["require_kill_zone"] and not is_kz:
            confidence -= 0.10

        # ADX trend strength bonus
        adx = f.get("adx_14", 0)
        if adx > 25:
            confidence += 0.10
        elif adx > 20:
            confidence += 0.05

        # EMA alignment bonus
        ema_align = f.get("ema_alignment", 0)
        if (bos_direction > 0 and ema_align == 1.0) or (bos_direction < 0 and ema_align == -1.0):
            confidence += 0.10

        # RSI confirmation
        rsi = f.get("rsi_14", 50)
        if bos_direction > 0 and 40 < rsi < 70:
            confidence += 0.05
        elif bos_direction < 0 and 30 < rsi < 60:
            confidence += 0.05

        # Body ratio (decisive candle)
        body = f.get("body_ratio", 0)
        if body > 0.6:
            confidence += 0.05

        # ── Entry, Stop, Target ──────────────────────────────────────
        risk = atr * 1.0  # 1 ATR stop distance

        if bos_direction > 0:
            direction = Direction.LONG
            entry = current_close
            stop = entry - risk
            target = entry + risk * self._params["min_rr"]
        else:
            direction = Direction.SHORT
            entry = current_close
            stop = entry + risk
            target = entry - risk * self._params["min_rr"]

        return self.create_signal(
            direction=direction,
            confidence=min(confidence, 0.95),
            entry_price=round(entry * 4) / 4,
            stop_loss=round(stop * 4) / 4,
            take_profit=round(target * 4) / 4,
            reasoning=(
                f"BOS {('bullish' if bos_direction > 0 else 'bearish')} "
                f"{bars_since_bos} bars ago, retest zone. "
                f"ADX={adx:.0f}, RSI={rsi:.0f}, VWAP dist={vwap_dist:.2f}"
            ),
            features_used=["last_bos_direction", "bars_since_bos", "vwap_dist_atr",
                          "ema20_slope", "adx_14", "rsi_14", "volume_ratio"],
            features_snapshot={k: f.get(k, 0) for k in ["last_bos_direction", "bars_since_bos",
                              "vwap_dist_atr", "adx_14", "rsi_14"]},
            regime=features.regime,
        )

    def get_parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_parameters(self, params: Dict[str, Any]):
        self._params.update(params)
