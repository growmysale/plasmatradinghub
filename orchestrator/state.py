"""Orchestrator State Persistence.

Saves and restores trading state across container restarts using
the existing SQLiteManager key-value store (system_state table).

Persisted state:
  - Account balances, daily counters, consecutive losses
  - Orchestrator metadata (mode, contract symbol, last trading day)
  - Daily summaries for consistency rule tracking
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.types import AccountState, TradingMode
from data_engine.database import get_sqlite

logger = logging.getLogger(__name__)


class OrchestratorState:
    """Persists orchestrator state to SQLite for recovery."""

    def __init__(self):
        self._db = get_sqlite()

    # ── Account State ─────────────────────────────────────────────────

    def save_account_state(self, account: AccountState):
        """Serialize and save AccountState."""
        self._db.set_state("account_state", {
            "balance": account.balance,
            "initial_balance": account.initial_balance,
            "peak_balance": account.peak_balance,
            "daily_pnl": account.daily_pnl,
            "daily_trades": account.daily_trades,
            "daily_wins": account.daily_wins,
            "daily_losses": account.daily_losses,
            "consecutive_losses": account.consecutive_losses,
            "max_loss_limit": account.max_loss_limit,
            "daily_loss_limit": account.daily_loss_limit,
            "daily_profit_target": account.daily_profit_target,
            "max_trades_per_day": account.max_trades_per_day,
            "mode": account.mode.value,
        })

    def load_account_state(self) -> Optional[AccountState]:
        """Load AccountState from SQLite."""
        data = self._db.get_state("account_state")
        if not data:
            return None

        try:
            return AccountState(
                balance=data["balance"],
                initial_balance=data["initial_balance"],
                peak_balance=data["peak_balance"],
                daily_pnl=data.get("daily_pnl", 0.0),
                daily_trades=data.get("daily_trades", 0),
                daily_wins=data.get("daily_wins", 0),
                daily_losses=data.get("daily_losses", 0),
                consecutive_losses=data.get("consecutive_losses", 0),
                max_loss_limit=data.get("max_loss_limit", 2000.0),
                daily_loss_limit=data.get("daily_loss_limit", 200.0),
                daily_profit_target=data.get("daily_profit_target", 300.0),
                max_trades_per_day=data.get("max_trades_per_day", 3),
                mode=TradingMode(data.get("mode", "sandbox")),
            )
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to load account state: {e}")
            return None

    # ── Orchestrator Metadata ─────────────────────────────────────────

    def save_orchestrator_meta(
        self,
        mode: TradingMode,
        contract_symbol: str,
        last_trading_day: str,
    ):
        """Save orchestrator metadata."""
        self._db.set_state("orchestrator_meta", {
            "mode": mode.value,
            "contract_symbol": contract_symbol,
            "last_trading_day": last_trading_day,
            "saved_at": datetime.now().isoformat(),
        })

    def load_orchestrator_meta(self) -> Optional[Dict[str, Any]]:
        """Load orchestrator metadata."""
        return self._db.get_state("orchestrator_meta")

    # ── Daily Summaries ───────────────────────────────────────────────

    def save_daily_summary(
        self,
        date_str: str,
        pnl: float,
        trades: int,
        wins: int,
        losses: int,
    ):
        """Save daily summary for consistency rule tracking."""
        self._db.set_state(f"daily_{date_str}", {
            "date": date_str,
            "pnl": round(pnl, 2),
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "saved_at": datetime.now().isoformat(),
        })
        logger.info(
            f"Daily summary saved: {date_str} PnL=${pnl:.2f} "
            f"Trades={trades} W={wins} L={losses}"
        )

    def get_daily_summary(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Get daily summary for a specific date."""
        return self._db.get_state(f"daily_{date_str}")
