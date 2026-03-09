"""Walk-Forward Backtesting Engine.

Simulates strategy execution on historical data with realistic fills,
slippage, commissions, and prop firm rule enforcement.

CRITICAL: Out-of-sample results are the ONLY results that matter.
In-sample performance is meaningless for trading.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from agents.base import StrategyAgent
from core.config import get_config
from core.types import AccountState, Direction, Signal, Trade, TradingMode
from feature_engine.engine import FeatureEngine

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    agent_id: str = ""
    train_start: Optional[datetime] = None
    train_end: Optional[datetime] = None
    test_start: Optional[datetime] = None
    test_end: Optional[datetime] = None

    # In-sample metrics
    is_total_trades: int = 0
    is_win_rate: float = 0.0
    is_profit_factor: float = 0.0
    is_sharpe: float = 0.0
    is_max_drawdown: float = 0.0
    is_expectancy: float = 0.0

    # Out-of-sample metrics (THIS IS WHAT MATTERS)
    oos_total_trades: int = 0
    oos_win_rate: float = 0.0
    oos_profit_factor: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_expectancy: float = 0.0

    # Walk-forward summary
    wf_num_windows: int = 0
    wf_avg_oos_sharpe: float = 0.0
    wf_std_oos_sharpe: float = 0.0
    wf_pct_profitable_windows: float = 0.0
    wf_worst_window_sharpe: float = 0.0

    # Monte Carlo
    mc_median_return: float = 0.0
    mc_5th_pct_return: float = 0.0
    mc_95th_pct_return: float = 0.0
    mc_probability_of_ruin: float = 0.0

    # Statistical significance
    p_value: float = 1.0
    is_significant: bool = False
    vs_random_sharpe: float = 0.0

    # All trades
    trades: List[Trade] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


def compute_metrics(pnls: List[float]) -> Dict[str, float]:
    """Compute trading performance metrics from P&L list."""
    if not pnls:
        return {
            "total_trades": 0, "total_pnl": 0, "win_rate": 0,
            "profit_factor": 0, "avg_win": 0, "avg_loss": 0,
            "max_drawdown": 0, "sharpe": 0, "sortino": 0,
            "expectancy": 0, "calmar": 0,
        }

    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]

    total_pnl = float(arr.sum())
    win_rate = len(wins) / len(arr) if len(arr) > 0 else 0

    gross_profit = wins.sum() if len(wins) > 0 else 0
    gross_loss = abs(losses.sum()) if len(losses) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    avg_win = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0

    # Max drawdown
    cum_pnl = np.cumsum(arr)
    peak = np.maximum.accumulate(cum_pnl)
    drawdowns = peak - cum_pnl
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0

    # Sharpe ratio (annualized, assuming daily)
    mean_ret = arr.mean()
    std_ret = arr.std()
    sharpe = float(mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0

    # Sortino (downside deviation only)
    downside = arr[arr < 0]
    downside_std = downside.std() if len(downside) > 0 else 1
    sortino = float(mean_ret / downside_std * np.sqrt(252)) if downside_std > 0 else 0

    expectancy = float(arr.mean())

    calmar = float(total_pnl / max_dd) if max_dd > 0 else 0

    return {
        "total_trades": len(arr),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "expectancy": round(expectancy, 2),
        "calmar": round(calmar, 4),
    }


class BacktestEngine:
    """Walk-forward backtesting engine with realistic fills."""

    def __init__(self):
        self.config = get_config()
        self.feature_engine = FeatureEngine()
        self.slippage_ticks = self.config.backtest.slippage_ticks
        self.commission = self.config.backtest.commission_per_side
        self.tick_value = 1.25    # MES tick value
        self.point_value = 5.0   # MES point value

    def run(
        self,
        agent: StrategyAgent,
        candles: pd.DataFrame,
        features: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """Run a single backtest on the full dataset."""
        if features is None:
            features = self.feature_engine.compute(candles)

        pnls = []
        trades = []
        signals = []
        equity = [self.config.prop_firm.initial_balance]
        balance = self.config.prop_firm.initial_balance
        peak = balance

        position = None  # Active trade
        daily_pnl = 0.0
        daily_trades = 0
        current_day = None

        for i in range(60, len(candles)):
            ts = candles["ts"].iloc[i] if "ts" in candles.columns else None
            day = ts.date() if ts else None

            # Daily reset
            if day != current_day:
                current_day = day
                daily_pnl = 0.0
                daily_trades = 0

            # Skip if daily limits hit
            if daily_pnl <= -self.config.personal_risk.pdll:
                equity.append(balance)
                continue
            if daily_pnl >= self.config.personal_risk.pdpt:
                equity.append(balance)
                continue
            if daily_trades >= self.config.personal_risk.max_trades_per_day:
                equity.append(balance)
                continue

            close = candles["close"].iloc[i]
            high = candles["high"].iloc[i]
            low = candles["low"].iloc[i]

            # Check existing position
            if position is not None:
                # Check stop loss
                hit_sl = False
                hit_tp = False

                if position.direction == Direction.LONG:
                    if low <= position.stop_loss:
                        hit_sl = True
                    elif high >= position.take_profit:
                        hit_tp = True
                else:
                    if high >= position.stop_loss:
                        hit_sl = True
                    elif low <= position.take_profit:
                        hit_tp = True

                if hit_sl or hit_tp:
                    if hit_sl:
                        exit_price = position.stop_loss
                    else:
                        exit_price = position.take_profit

                    # Apply slippage
                    slippage = np.random.uniform(0, self.slippage_ticks) * 0.25
                    if position.direction == Direction.LONG:
                        exit_price -= slippage if hit_sl else -slippage
                    else:
                        exit_price += slippage if hit_sl else -slippage

                    # Calculate P&L
                    if position.direction == Direction.LONG:
                        pnl = (exit_price - position.entry_price) * self.point_value
                    else:
                        pnl = (position.entry_price - exit_price) * self.point_value

                    pnl -= self.commission * 2  # Round trip

                    position.exit_price = exit_price
                    position.pnl = pnl
                    position.ts_close = ts

                    pnls.append(pnl)
                    trades.append(position)
                    balance += pnl
                    daily_pnl += pnl
                    peak = max(peak, balance)
                    position = None

            # Generate signal if flat
            if position is None:
                # Check drawdown
                if peak - balance >= self.config.prop_firm.max_loss_limit:
                    equity.append(balance)
                    continue

                fv = self.feature_engine.compute_feature_vector(
                    candles.iloc[max(0, i - 200):i + 1], -1
                )

                signal = agent.on_features(fv, candles.iloc[max(0, i - 100):i + 1])

                if signal is not None:
                    signals.append(signal)

                    # Check R:R
                    if signal.risk_reward_ratio < self.config.personal_risk.min_risk_reward:
                        continue

                    # Open position with slippage
                    slippage = np.random.uniform(0, self.slippage_ticks) * 0.25
                    entry = signal.entry_price
                    if signal.direction == Direction.LONG:
                        entry += slippage
                    else:
                        entry -= slippage

                    position = Trade(
                        ts_open=ts,
                        symbol="MES",
                        direction=signal.direction,
                        entry_price=entry,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        agent_signals_used=[signal.id],
                        combined_confidence=signal.confidence,
                        regime=fv.regime,
                        atr_at_entry=fv.atr_14,
                        mode=TradingMode.SANDBOX,
                    )
                    daily_trades += 1

            equity.append(balance)

        # Close any open position at end
        if position is not None:
            close_price = candles["close"].iloc[-1]
            if position.direction == Direction.LONG:
                pnl = (close_price - position.entry_price) * self.point_value
            else:
                pnl = (position.entry_price - close_price) * self.point_value
            pnl -= self.commission * 2
            pnls.append(pnl)
            balance += pnl

        metrics = compute_metrics(pnls)

        result = BacktestResult(
            agent_id=agent.agent_id,
            is_total_trades=metrics["total_trades"],
            is_win_rate=metrics["win_rate"],
            is_profit_factor=metrics["profit_factor"],
            is_sharpe=metrics["sharpe"],
            is_max_drawdown=metrics["max_drawdown"],
            is_expectancy=metrics["expectancy"],
            trades=trades,
            signals=signals,
            equity_curve=equity,
            params=agent.get_parameters(),
        )

        return result

    def walk_forward(
        self,
        agent: StrategyAgent,
        candles: pd.DataFrame,
        train_days: int = 60,
        test_days: int = 5,
    ) -> BacktestResult:
        """Walk-forward validation: train on window A, test on window B, slide."""
        if "ts" not in candles.columns:
            logger.error("Need 'ts' column for walk-forward")
            return BacktestResult(agent_id=agent.agent_id)

        candles = candles.copy()
        candles["ts"] = pd.to_datetime(candles["ts"])
        candles["date"] = candles["ts"].dt.date

        dates = sorted(candles["date"].unique())
        if len(dates) < train_days + test_days:
            logger.error(f"Not enough data for walk-forward: {len(dates)} days < {train_days + test_days}")
            return BacktestResult(agent_id=agent.agent_id)

        window_results = []
        all_oos_pnls = []
        all_oos_trades = []
        all_signals = []

        step = 0
        while step + train_days + test_days <= len(dates):
            train_dates = dates[step:step + train_days]
            test_dates = dates[step + train_days:step + train_days + test_days]

            train_mask = candles["date"].isin(train_dates)
            test_mask = candles["date"].isin(test_dates)

            train_data = candles[train_mask].copy()
            test_data = candles[test_mask].copy()

            if len(test_data) < 10:
                step += test_days
                continue

            # Run backtest on test (OOS) data
            oos_result = self.run(agent, test_data)

            oos_pnls = [t.pnl for t in oos_result.trades]
            all_oos_pnls.extend(oos_pnls)
            all_oos_trades.extend(oos_result.trades)
            all_signals.extend(oos_result.signals)

            oos_metrics = compute_metrics(oos_pnls)
            window_results.append(oos_metrics)

            step += test_days

        if not window_results:
            return BacktestResult(agent_id=agent.agent_id)

        # Aggregate walk-forward results
        oos_metrics = compute_metrics(all_oos_pnls)

        oos_sharpes = [w["sharpe"] for w in window_results]
        profitable_windows = sum(1 for w in window_results if w["total_pnl"] > 0)

        # Monte Carlo
        mc_results = self._monte_carlo(all_oos_pnls)

        # Statistical significance (vs random)
        p_value = self._significance_test(all_oos_pnls)

        result = BacktestResult(
            agent_id=agent.agent_id,
            oos_total_trades=oos_metrics["total_trades"],
            oos_win_rate=oos_metrics["win_rate"],
            oos_profit_factor=oos_metrics["profit_factor"],
            oos_sharpe=oos_metrics["sharpe"],
            oos_max_drawdown=oos_metrics["max_drawdown"],
            oos_expectancy=oos_metrics["expectancy"],
            wf_num_windows=len(window_results),
            wf_avg_oos_sharpe=round(float(np.mean(oos_sharpes)), 4) if oos_sharpes else 0,
            wf_std_oos_sharpe=round(float(np.std(oos_sharpes)), 4) if oos_sharpes else 0,
            wf_pct_profitable_windows=round(profitable_windows / len(window_results), 4),
            wf_worst_window_sharpe=round(float(min(oos_sharpes)), 4) if oos_sharpes else 0,
            mc_median_return=mc_results.get("median", 0),
            mc_5th_pct_return=mc_results.get("p5", 0),
            mc_95th_pct_return=mc_results.get("p95", 0),
            mc_probability_of_ruin=mc_results.get("ruin_prob", 0),
            p_value=p_value,
            is_significant=p_value < self.config.backtest.significance_level,
            trades=all_oos_trades,
            signals=all_signals,
            params=agent.get_parameters(),
        )

        return result

    def _monte_carlo(self, pnls: List[float], n_sims: int = 1000) -> Dict[str, float]:
        """Monte Carlo simulation: shuffle trade order, check distribution."""
        if len(pnls) < 5:
            return {"median": 0, "p5": 0, "p95": 0, "ruin_prob": 0}

        arr = np.array(pnls)
        total_returns = []

        for _ in range(n_sims):
            shuffled = np.random.permutation(arr)
            cum = np.cumsum(shuffled)
            total_returns.append(cum[-1])

        total_returns = np.array(total_returns)
        ruin_threshold = -self.config.prop_firm.max_loss_limit

        # Check if any path hits ruin
        ruin_count = 0
        for _ in range(n_sims):
            shuffled = np.random.permutation(arr)
            cum = np.cumsum(shuffled)
            if cum.min() <= ruin_threshold:
                ruin_count += 1

        return {
            "median": round(float(np.median(total_returns)), 2),
            "p5": round(float(np.percentile(total_returns, 5)), 2),
            "p95": round(float(np.percentile(total_returns, 95)), 2),
            "ruin_prob": round(ruin_count / n_sims, 4),
        }

    def _significance_test(self, pnls: List[float]) -> float:
        """Test if returns are significantly different from zero."""
        if len(pnls) < 5:
            return 1.0

        arr = np.array(pnls)
        t_stat, p_value = stats.ttest_1samp(arr, 0)
        # One-sided: we want positive returns
        if arr.mean() > 0:
            p_value = p_value / 2
        else:
            p_value = 1 - p_value / 2

        return round(float(p_value), 6)
