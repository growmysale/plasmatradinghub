"""Sandbox Execution Engine.

Three modes sharing the same code path:
  SANDBOX: Historical replay with sim fills
  PAPER: Live data with sim fills
  LIVE: Real execution (future)

Fill simulation model:
  - Market orders: fill at ask (buy) or bid (sell) + random slippage
  - Limit orders: fill when price crosses, 30% miss rate
  - Stop orders: fill at stop + slippage
  - Commission: $0.00 on TopstepX
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from core.config import get_config
from core.events import Event, EventBus, EventType, get_event_bus
from core.types import (
    AccountState, Candle, CombinedSignal, Direction, Order, OrderStatus,
    OrderType, Trade, TradingMode,
)

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    """Result of order fill simulation."""
    filled: bool = False
    fill_price: float = 0.0
    slippage_ticks: float = 0.0
    reason: str = ""


class ExecutionEngine:
    """Handles order execution across all modes."""

    def __init__(self, mode: TradingMode = TradingMode.SANDBOX):
        self.config = get_config()
        self.mode = mode
        self.account = AccountState(
            balance=self.config.prop_firm.initial_balance,
            initial_balance=self.config.prop_firm.initial_balance,
            peak_balance=self.config.prop_firm.initial_balance,
            max_loss_limit=self.config.prop_firm.max_loss_limit,
            daily_loss_limit=self.config.personal_risk.pdll,
            daily_profit_target=self.config.personal_risk.pdpt,
            max_trades_per_day=self.config.personal_risk.max_trades_per_day,
            mode=mode,
        )

        self._active_orders: List[Order] = []
        self._trade_history: List[Trade] = []
        self._equity_curve: List[float] = [self.account.balance]
        self._callbacks: Dict[str, List[Callable]] = {
            "on_fill": [],
            "on_position_open": [],
            "on_position_close": [],
            "on_risk_alert": [],
        }
        self._current_day: Optional[str] = None

    def register_callback(self, event: str, callback: Callable):
        """Register a callback for execution events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def submit_order(self, order: Order, current_candle: Candle) -> FillResult:
        """Submit an order for execution.

        In sandbox/paper mode, simulates fill. In live mode, would
        route to broker API.
        """
        if self.mode == TradingMode.LIVE:
            # TODO: Route to Tradovate API
            logger.warning("Live execution not yet implemented")
            return FillResult(filled=False, reason="Live mode not implemented")

        return self._simulate_fill(order, current_candle)

    def _simulate_fill(self, order: Order, candle: Candle) -> FillResult:
        """Simulate order fill with realistic slippage."""
        if order.order_type == OrderType.MARKET:
            # Fill at current price + random slippage
            slippage = np.random.uniform(0, 0.5) * 0.25  # 0 to 0.5 ticks
            if order.direction == Direction.LONG:
                fill_price = candle.close + slippage
            else:
                fill_price = candle.close - slippage

            return FillResult(
                filled=True,
                fill_price=round(fill_price * 4) / 4,
                slippage_ticks=slippage / 0.25,
            )

        elif order.order_type == OrderType.LIMIT:
            # Check if price reached limit level
            if order.direction == Direction.LONG and candle.low <= order.price:
                # 30% miss rate
                if np.random.random() < 0.30:
                    return FillResult(filled=False, reason="Limit order not filled (miss rate)")
                return FillResult(filled=True, fill_price=order.price, slippage_ticks=0)

            elif order.direction == Direction.SHORT and candle.high >= order.price:
                if np.random.random() < 0.30:
                    return FillResult(filled=False, reason="Limit order not filled (miss rate)")
                return FillResult(filled=True, fill_price=order.price, slippage_ticks=0)

            return FillResult(filled=False, reason="Price did not reach limit level")

        elif order.order_type == OrderType.STOP:
            slippage = np.random.uniform(0, 1.0) * 0.25
            if order.direction == Direction.LONG and candle.high >= order.price:
                return FillResult(
                    filled=True,
                    fill_price=round((order.price + slippage) * 4) / 4,
                    slippage_ticks=slippage / 0.25,
                )
            elif order.direction == Direction.SHORT and candle.low <= order.price:
                return FillResult(
                    filled=True,
                    fill_price=round((order.price - slippage) * 4) / 4,
                    slippage_ticks=slippage / 0.25,
                )
            return FillResult(filled=False, reason="Stop not triggered")

        return FillResult(filled=False, reason="Unknown order type")

    def open_position(self, order: Order, fill: FillResult, ts: datetime) -> Trade:
        """Open a new position from a filled order."""
        trade = Trade(
            ts_open=ts,
            symbol=order.symbol,
            direction=order.direction,
            entry_price=fill.fill_price,
            quantity=order.quantity,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            agent_signals_used=order.agent_signals_used,
            combined_confidence=order.combined_confidence,
            intended_entry=order.price,
            actual_entry=fill.fill_price,
            entry_slippage=fill.slippage_ticks * 0.25,
            account_balance_before=self.account.balance,
            daily_pnl_before=self.account.daily_pnl,
            mode=self.mode,
        )

        self.account.open_position = trade
        self.account.daily_trades += 1

        for cb in self._callbacks.get("on_position_open", []):
            cb(trade)

        return trade

    def check_position(self, candle: Candle) -> Optional[Trade]:
        """Check if open position hit SL/TP and close if so."""
        pos = self.account.open_position
        if pos is None:
            return None

        hit_sl = False
        hit_tp = False

        if pos.direction == Direction.LONG:
            if candle.low <= pos.stop_loss:
                hit_sl = True
            elif candle.high >= pos.take_profit:
                hit_tp = True
        else:
            if candle.high >= pos.stop_loss:
                hit_sl = True
            elif candle.low <= pos.take_profit:
                hit_tp = True

        if not hit_sl and not hit_tp:
            return None

        # Close position
        if hit_sl:
            exit_price = pos.stop_loss
            slippage = np.random.uniform(0, 0.5) * 0.25
            if pos.direction == Direction.LONG:
                exit_price -= slippage
            else:
                exit_price += slippage
        else:
            exit_price = pos.take_profit

        return self.close_position(exit_price, candle.ts)

    def close_position(self, exit_price: float, ts: datetime) -> Optional[Trade]:
        """Close the current position."""
        pos = self.account.open_position
        if pos is None:
            return None

        exit_price = round(exit_price * 4) / 4

        if pos.direction == Direction.LONG:
            pnl = (exit_price - pos.entry_price) * 5.0 * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * 5.0 * pos.quantity

        # Commission (TopstepX = free)
        commission = 0.0
        pnl -= commission

        pos.exit_price = exit_price
        pos.pnl = round(pnl, 2)
        pos.pnl_ticks = round((exit_price - pos.entry_price) / 0.25, 1)
        pos.commission = commission
        pos.ts_close = ts
        pos.account_balance_after = self.account.balance + pnl
        pos.daily_pnl_after = self.account.daily_pnl + pnl
        pos.max_loss_limit_distance = self.account.distance_to_max_loss

        # Update account
        self.account.balance += pnl
        self.account.daily_pnl += pnl
        self.account.peak_balance = max(self.account.peak_balance, self.account.balance)
        self.account.open_position = None

        if pnl > 0:
            self.account.daily_wins += 1
            self.account.consecutive_losses = 0
        else:
            self.account.daily_losses += 1
            self.account.consecutive_losses += 1

        self._trade_history.append(pos)
        self._equity_curve.append(self.account.balance)

        for cb in self._callbacks.get("on_position_close", []):
            cb(pos)

        return pos

    def process_candle(self, candle: Candle) -> Optional[Trade]:
        """Process a new candle - check positions, update state."""
        # Day change detection
        day = candle.ts.strftime("%Y-%m-%d") if isinstance(candle.ts, datetime) else str(candle.ts)[:10]
        if day != self._current_day:
            self._current_day = day
            self.account.daily_pnl = 0.0
            self.account.daily_trades = 0
            self.account.daily_wins = 0
            self.account.daily_losses = 0

        return self.check_position(candle)

    def flatten_all(self, current_price: float, ts: datetime, reason: str = ""):
        """Emergency flatten - close all positions immediately."""
        logger.warning(f"FLATTEN ALL: {reason}")
        if self.account.open_position:
            self.close_position(current_price, ts)

        for cb in self._callbacks.get("on_risk_alert", []):
            cb({"action": "flatten", "reason": reason})

    def get_trade_history(self) -> List[Trade]:
        return list(self._trade_history)

    def get_equity_curve(self) -> List[float]:
        return list(self._equity_curve)

    def get_account_state(self) -> AccountState:
        return self.account

    def reset(self):
        """Reset to initial state."""
        self.account = AccountState(
            balance=self.config.prop_firm.initial_balance,
            initial_balance=self.config.prop_firm.initial_balance,
            peak_balance=self.config.prop_firm.initial_balance,
            mode=self.mode,
        )
        self._trade_history.clear()
        self._equity_curve = [self.account.balance]
        self._current_day = None
