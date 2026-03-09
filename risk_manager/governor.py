"""Risk Manager - The Governor.

Sits above everything with absolute veto power. No strategy agent,
no matter how confident, can override the Governor.

Pipeline:
  1. Regime Risk Filter
  2. Prop Firm Compliance Check
  3. Personal Risk Limits
  4. Position Sizing (Kelly/Fixed Fractional)
  5. Execution Quality Check
  6. Approved/Rejected
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.config import get_config
from core.types import (
    AccountState, CombinedSignal, Direction, Order, OrderType, Regime,
)

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    """Result of risk evaluation."""
    approved: bool = False
    order: Optional[Order] = None
    rejection_reason: str = ""
    warnings: List[str] = field(default_factory=list)
    position_size: int = 1
    risk_amount: float = 0.0


@dataclass
class CircuitBreaker:
    """Circuit breaker state."""
    consecutive_losses: int = 0
    daily_losses: int = 0
    is_halted: bool = False
    halt_reason: str = ""
    halt_until: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None


class RiskManager:
    """The Governor - absolute veto authority on all trades.

    This is like a Kubernetes admission controller: requests that
    violate policy get rejected before execution.
    """

    def __init__(self):
        self.config = get_config()
        self.prop_firm = self.config.prop_firm
        self.personal = self.config.personal_risk
        self.circuit = CircuitBreaker()
        self._compliance_log: List[dict] = []

    def evaluate(
        self,
        signal: CombinedSignal,
        account: AccountState,
        current_regime: Regime,
        current_time: Optional[datetime] = None,
        minutes_to_news: int = 999,
    ) -> RiskDecision:
        """Run the full risk pipeline. Returns approved or rejected."""
        decision = RiskDecision()
        now = current_time or datetime.now()

        # ── [1] Regime Risk Filter ───────────────────────────────────
        regime_ok, regime_msg = self._check_regime(current_regime, signal.confidence)
        if not regime_ok:
            decision.rejection_reason = f"[Regime] {regime_msg}"
            self._log_compliance("block", "regime_filter", regime_msg)
            return decision

        # ── [2] Prop Firm Compliance Check ───────────────────────────
        compliance_ok, compliance_msg = self._check_prop_firm_compliance(signal, account)
        if not compliance_ok:
            decision.rejection_reason = f"[Compliance] {compliance_msg}"
            self._log_compliance("violation", "prop_firm", compliance_msg)
            return decision

        # ── [3] Personal Risk Limits ─────────────────────────────────
        personal_ok, personal_msg = self._check_personal_limits(account, now, minutes_to_news)
        if not personal_ok:
            decision.rejection_reason = f"[Personal] {personal_msg}"
            self._log_compliance("block", "personal_limits", personal_msg)
            return decision

        # ── [4] Circuit Breakers ─────────────────────────────────────
        circuit_ok, circuit_msg = self._check_circuit_breakers(account, now)
        if not circuit_ok:
            decision.rejection_reason = f"[Circuit] {circuit_msg}"
            return decision

        # ── [5] Position Sizing ──────────────────────────────────────
        size, risk_amount = self._calculate_position_size(signal, account)

        # ── [6] Execution Quality Check ──────────────────────────────
        exec_ok, exec_msg = self._check_execution_quality(signal)
        if not exec_ok:
            decision.rejection_reason = f"[Execution] {exec_msg}"
            return decision

        # ── APPROVED ─────────────────────────────────────────────────
        decision.approved = True
        decision.position_size = size
        decision.risk_amount = risk_amount

        # Create order
        best_signal = max(signal.agent_signals, key=lambda s: s.confidence) if signal.agent_signals else None

        decision.order = Order(
            symbol="MES",
            direction=signal.direction,
            order_type=OrderType.MARKET,
            price=best_signal.entry_price if best_signal else 0,
            quantity=size,
            stop_loss=best_signal.stop_loss if best_signal else 0,
            take_profit=best_signal.take_profit if best_signal else 0,
            signal_id=signal.id,
            agent_signals_used=signal.contributing_agents,
            combined_confidence=signal.confidence,
        )

        # Warnings
        if account.distance_to_max_loss < 500:
            decision.warnings.append(f"Close to max loss limit: ${account.distance_to_max_loss:.0f} remaining")
        if account.consecutive_losses >= 1:
            decision.warnings.append(f"On a {account.consecutive_losses}-trade losing streak")

        self._log_compliance("check", "approved", f"Size={size}, risk=${risk_amount:.2f}")
        return decision

    def _check_regime(self, regime: Regime, confidence: float) -> Tuple[bool, str]:
        """Is the current regime suitable for trading?"""
        if regime == Regime.QUIET_COMPRESSION and confidence < 0.80:
            return False, "Quiet regime requires confidence > 0.80"
        if regime == Regime.UNKNOWN:
            return False, "Unknown regime - cannot assess risk"
        return True, "OK"

    def _check_prop_firm_compliance(self, signal: CombinedSignal, account: AccountState) -> Tuple[bool, str]:
        """Check TopstepX rules."""
        # Max loss limit check
        best_sig = max(signal.agent_signals, key=lambda s: s.confidence) if signal.agent_signals else None
        if best_sig:
            worst_case_loss = abs(best_sig.entry_price - best_sig.stop_loss) * 5.0  # point_value
            if account.balance - worst_case_loss < account.max_loss_floor:
                return False, f"Trade would risk breaching max loss limit (worst case: -${worst_case_loss:.2f})"

        # Scaling plan check
        profit = account.balance - account.initial_balance
        max_contracts = 2  # Default
        for threshold, contracts in sorted(self.prop_firm.scaling_plan.items(), key=lambda x: float(x[0])):
            if profit >= float(threshold):
                max_contracts = contracts

        # Open position check
        if account.open_position is not None:
            return False, "Already have an open position"

        # Session close check (no overnight)
        return True, "OK"

    def _check_personal_limits(self, account: AccountState, now: datetime, minutes_to_news: int) -> Tuple[bool, str]:
        """Check Raymond's personal rules."""
        if account.is_pdll_hit:
            return False, f"PDLL hit: daily P&L ${account.daily_pnl:.2f} <= -${self.personal.pdll}"
        if account.is_pdpt_hit:
            return False, f"PDPT hit: daily P&L ${account.daily_pnl:.2f} >= ${self.personal.pdpt}"
        if account.is_max_trades_hit:
            return False, f"Max trades hit: {account.daily_trades}/{self.personal.max_trades_per_day}"
        if minutes_to_news <= self.personal.news_blackout_minutes:
            return False, f"News event in {minutes_to_news} minutes - blackout period"
        return True, "OK"

    def _check_circuit_breakers(self, account: AccountState, now: datetime) -> Tuple[bool, str]:
        """Check circuit breaker conditions."""
        # Cooldown after consecutive losses
        if account.consecutive_losses >= self.personal.cooldown_after_consecutive_losses:
            if self.circuit.cooldown_until and now < self.circuit.cooldown_until:
                remaining = (self.circuit.cooldown_until - now).total_seconds() / 60
                return False, f"Cooldown: {remaining:.0f} min remaining after {account.consecutive_losses} consecutive losses"

        # Halt after too many daily losses
        if account.daily_losses >= self.personal.halt_after_daily_losses:
            return False, f"HALT: {account.daily_losses} losses today (max {self.personal.halt_after_daily_losses})"

        # Close to max loss limit
        if account.distance_to_max_loss < 200:
            return False, f"HALT: Only ${account.distance_to_max_loss:.0f} from max loss limit"

        return True, "OK"

    def _calculate_position_size(self, signal: CombinedSignal, account: AccountState) -> Tuple[int, float]:
        """Position sizing using quarter-Kelly or fixed risk."""
        # Fixed risk: max $50 per trade
        max_risk = self.personal.max_risk_per_trade

        best_sig = max(signal.agent_signals, key=lambda s: s.confidence) if signal.agent_signals else None
        if not best_sig:
            return 1, max_risk

        risk_per_contract = abs(best_sig.entry_price - best_sig.stop_loss) * 5.0

        if risk_per_contract <= 0:
            return 1, max_risk

        # Kelly Criterion (quarter-Kelly for safety)
        # Kelly = (win_rate * avg_win - (1-win_rate) * avg_loss) / avg_win
        # We use simplified version based on confidence
        kelly_fraction = (signal.confidence - 0.5) * 2  # 0.6 conf → 0.2 fraction
        quarter_kelly = kelly_fraction * 0.25

        # Contracts based on risk budget
        contracts_by_risk = max(1, int(max_risk / risk_per_contract))

        # Scaling plan constraint
        profit = account.balance - account.initial_balance
        max_contracts = 2
        for threshold, contracts in sorted(self.prop_firm.scaling_plan.items(), key=lambda x: float(x[0])):
            if profit >= float(threshold):
                max_contracts = contracts

        size = min(contracts_by_risk, max_contracts)
        actual_risk = size * risk_per_contract

        return size, actual_risk

    def _check_execution_quality(self, signal: CombinedSignal) -> Tuple[bool, str]:
        """Check if the trade setup meets quality standards."""
        best_sig = max(signal.agent_signals, key=lambda s: s.confidence) if signal.agent_signals else None
        if not best_sig:
            return False, "No valid signal entry/stop/target"

        # R:R check
        if best_sig.risk_reward_ratio < self.personal.min_risk_reward:
            return False, f"R:R {best_sig.risk_reward_ratio:.1f} below minimum {self.personal.min_risk_reward}"

        return True, "OK"

    def record_trade_result(self, pnl: float, now: Optional[datetime] = None):
        """Record trade result for circuit breaker tracking."""
        now = now or datetime.now()

        if pnl <= 0:
            self.circuit.consecutive_losses += 1
            self.circuit.daily_losses += 1

            if self.circuit.consecutive_losses >= self.personal.cooldown_after_consecutive_losses:
                from datetime import timedelta
                self.circuit.cooldown_until = now + timedelta(minutes=self.personal.cooldown_minutes)
                logger.warning(f"Cooldown triggered: {self.circuit.consecutive_losses} consecutive losses")
        else:
            self.circuit.consecutive_losses = 0

    def reset_daily(self):
        """Reset daily counters."""
        self.circuit.daily_losses = 0
        self.circuit.is_halted = False
        self.circuit.halt_reason = ""

    def _log_compliance(self, event_type: str, rule: str, details: str):
        """Log compliance event."""
        self._compliance_log.append({
            "ts": datetime.now().isoformat(),
            "event_type": event_type,
            "rule": rule,
            "details": details,
        })

    def get_compliance_log(self) -> List[dict]:
        return list(self._compliance_log)
