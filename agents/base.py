"""Strategy Agent Base Class.

Every strategy agent implements this interface. Agents are independent -
they don't know about each other. The Allocator (Layer 3) combines
their signals. Each agent is a portfolio manager at a multi-strat fund.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from core.types import (
    AccountState, AgentStats, Direction, FeatureVector, Regime, Signal,
)


class StrategyAgent(ABC):
    """Base class for all strategy agents."""

    agent_id: str = ""
    agent_name: str = ""
    version: str = "1.0"
    preferred_regimes: List[Regime] = []
    min_confidence_threshold: float = 0.55

    def __init__(self):
        self._params: Dict[str, Any] = {}

    @abstractmethod
    def on_features(self, features: FeatureVector, candles: pd.DataFrame) -> Optional[Signal]:
        """Called on every new candle close with updated features.

        Args:
            features: Current feature vector for this bar.
            candles: Recent candle data (for lookback calculations).

        Returns:
            A Signal if the agent sees an opportunity, or None.
        """
        pass

    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Return current strategy parameters for optimization."""
        pass

    @abstractmethod
    def set_parameters(self, params: Dict[str, Any]):
        """Update strategy parameters for walk-forward optimization."""
        pass

    def should_be_active(self, current_regime: Regime) -> bool:
        """Is this agent suited for the current market regime?"""
        if not self.preferred_regimes:
            return True
        return current_regime in self.preferred_regimes

    def create_signal(
        self,
        direction: Direction,
        confidence: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        reasoning: str,
        features_used: List[str] = None,
        features_snapshot: Dict[str, float] = None,
        regime: Regime = Regime.UNKNOWN,
    ) -> Optional[Signal]:
        """Helper to create a signal with validation."""
        if confidence < self.min_confidence_threshold:
            return None

        if direction == Direction.FLAT:
            return None

        # Calculate R:R
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr = reward / risk if risk > 0 else 0

        return Signal(
            agent_id=self.agent_id,
            agent_version=self.version,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=round(rr, 2),
            reasoning=reasoning,
            features_used=features_used or [],
            features_snapshot=features_snapshot or {},
            regime_at_signal=regime,
        )

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.agent_id})>"
