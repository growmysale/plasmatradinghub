"""Meta-Strategy Allocator - The Brain.

Receives signals from all active agents and produces a single combined
decision. Multiple combination methods are available.

Methods:
  1. Weighted Vote - weight by OOS Sharpe
  2. Regime-Conditional - only active agents for current regime
  3. Unanimous Consent - 3+ agents must agree
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from core.config import get_config
from core.types import CombinedSignal, Direction, Regime, Signal

logger = logging.getLogger(__name__)


class Allocator:
    """Meta-strategy that combines signals from multiple agents."""

    def __init__(self):
        self.config = get_config().allocator
        self._weights: Dict[str, float] = {}
        self._last_loss_bar = -999
        self._cooldown_bars = 3

    def set_weights(self, weights: Dict[str, float]):
        """Set agent weights (from performance tracking)."""
        self._weights = weights

    def get_weights(self) -> Dict[str, float]:
        return dict(self._weights)

    def combine_signals(
        self,
        signals: List[Signal],
        current_regime: Regime,
        method: Optional[str] = None,
    ) -> Optional[CombinedSignal]:
        """Combine multiple agent signals into a single decision.

        Args:
            signals: List of signals from active agents.
            current_regime: Current market regime.
            method: Override combination method.

        Returns:
            CombinedSignal if a trade should be taken, None otherwise.
        """
        if not signals:
            return None

        method = method or self.config.combination_method

        if method == "weighted_vote":
            return self._weighted_vote(signals, current_regime)
        elif method == "regime_conditional":
            return self._regime_conditional(signals, current_regime)
        elif method == "unanimous":
            return self._unanimous_consent(signals, current_regime)
        else:
            return self._weighted_vote(signals, current_regime)

    def _weighted_vote(self, signals: List[Signal], regime: Regime) -> Optional[CombinedSignal]:
        """Weighted vote combination."""
        if not signals:
            return None

        long_score = 0.0
        short_score = 0.0
        contributing = []

        for sig in signals:
            weight = self._weights.get(sig.agent_id, 1.0 / len(signals))

            if sig.direction == Direction.LONG:
                long_score += weight * sig.confidence
                contributing.append(sig.agent_id)
            elif sig.direction == Direction.SHORT:
                short_score += weight * sig.confidence
                contributing.append(sig.agent_id)

        # Direction from weighted vote
        if long_score > short_score and long_score > self.config.min_combined_confidence:
            direction = Direction.LONG
            confidence = long_score
        elif short_score > long_score and short_score > self.config.min_combined_confidence:
            direction = Direction.SHORT
            confidence = short_score
        else:
            return None

        # Conflict check
        if abs(long_score - short_score) < self.config.conflict_threshold:
            return None  # Conflicting signals → stay flat

        # Pick best signal for entry/stop/target
        best_signal = max(
            [s for s in signals if s.direction == direction],
            key=lambda s: s.confidence * self._weights.get(s.agent_id, 0.1),
        )

        return CombinedSignal(
            direction=direction,
            confidence=min(confidence, 0.95),
            contributing_agents=contributing,
            agent_signals=signals,
            reasoning=f"Weighted vote: L={long_score:.3f} S={short_score:.3f}, "
                      f"{len(contributing)} agents, regime={regime.value}",
            regime=regime,
        )

    def _regime_conditional(self, signals: List[Signal], regime: Regime) -> Optional[CombinedSignal]:
        """Only consider agents suited for current regime."""
        # Filter to agents that prefer this regime
        regime_agents = {
            Regime.TRENDING_UP: {"smc_br", "orb", "momentum", "ob_fvg"},
            Regime.TRENDING_DOWN: {"smc_br", "orb", "momentum", "ob_fvg"},
            Regime.RANGING: {"vwap_mr", "ob_fvg"},
            Regime.VOLATILE_EXPANSION: {"orb", "xgb_classifier", "rl_ppo"},
            Regime.QUIET_COMPRESSION: set(),  # Don't trade in quiet regimes
            Regime.UNKNOWN: set(),
        }

        active_ids = regime_agents.get(regime, set())
        if not active_ids:
            return None

        filtered = [s for s in signals if s.agent_id in active_ids]
        if not filtered:
            return None

        return self._weighted_vote(filtered, regime)

    def _unanimous_consent(self, signals: List[Signal], regime: Regime) -> Optional[CombinedSignal]:
        """Only trade when 3+ agents agree on direction."""
        min_agents = self.config.unanimous_min_agents

        direction_counts = defaultdict(list)
        for sig in signals:
            if sig.direction != Direction.FLAT:
                direction_counts[sig.direction].append(sig)

        for direction, sigs in direction_counts.items():
            if len(sigs) >= min_agents:
                avg_conf = np.mean([s.confidence for s in sigs])
                if avg_conf >= 0.60:
                    best = max(sigs, key=lambda s: s.confidence)
                    return CombinedSignal(
                        direction=direction,
                        confidence=min(avg_conf, 0.95),
                        contributing_agents=[s.agent_id for s in sigs],
                        agent_signals=signals,
                        reasoning=f"Unanimous: {len(sigs)} agents agree on {direction.value}, "
                                  f"avg confidence={avg_conf:.3f}",
                        regime=regime,
                    )

        return None

    def update_weights_from_performance(self, agent_stats: Dict[str, dict]):
        """Update agent weights based on rolling OOS performance."""
        if not agent_stats:
            return

        # Weight by OOS Sharpe ratio
        sharpes = {}
        for agent_id, stats in agent_stats.items():
            sharpe = stats.get("oos_sharpe", 0)
            # Only positive Sharpe agents get weight
            sharpes[agent_id] = max(sharpe, 0.01)

        total = sum(sharpes.values())
        if total > 0:
            self._weights = {k: v / total for k, v in sharpes.items()}
        else:
            # Equal weight
            n = len(agent_stats)
            self._weights = {k: 1.0 / n for k in agent_stats}

        logger.info(f"Updated agent weights: {self._weights}")
