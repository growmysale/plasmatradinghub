"""PropEdge Trading Orchestrator — The Real-Time Trading Loop.

Ties all layers into a live pipeline:
  Market Data → Features → Agents → Allocator → Risk → Execution

Mirrors the backtester loop (backtester/engine.py lines 171-317) but
runs asynchronously on real-time data from Tradovate WebSocket.

Modes:
  SANDBOX: Replay stored candles from CandleStore at configurable speed.
  PAPER:   Tradovate demo WebSocket for candles, simulated fills.
  LIVE:    Tradovate live WebSocket for candles, real order execution.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import pandas as pd

from core.config import get_config
from core.events import Event, EventType, get_event_bus
from core.types import (
    AccountState, Candle, CombinedSignal, Direction,
    Order, Regime, Signal, Trade, TradingMode,
)
from data_engine.candle_store import CandleStore
from data_engine.tradovate import TradovateClient, TradovateConfig
from feature_engine.engine import FeatureEngine
from feature_engine.regime import RegimeDetector
from agents.registry import get_all_agents
from allocator.meta_strategy import Allocator
from risk_manager.governor import RiskManager
from execution.sandbox import ExecutionEngine
from orchestrator.contract_resolver import ContractResolver
from orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


# ── Status & Metrics ────────────────────────────────────────────────────

class OrchestratorStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    PAUSED = "paused"
    SHUTDOWN = "shutdown"


@dataclass
class LoopMetrics:
    """Tracks orchestrator metrics for observability."""
    candles_processed: int = 0
    signals_generated: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    last_candle_ts: Optional[str] = None
    last_error: Optional[str] = None
    start_time: Optional[str] = None


# ── Main Orchestrator ────────────────────────────────────────────────────

class TradingOrchestrator:
    """Main real-time trading loop.

    Orchestrates the full pipeline:
    market data → features → agents → allocator → risk → execution

    Usage:
        orchestrator = TradingOrchestrator(
            mode=TradingMode.SANDBOX,
            broadcast_fn=broadcast_ws,
        )
        await orchestrator.start()
    """

    # MES session times (Central Time)
    # CME Globex: Sunday 5 PM CT to Friday 4 PM CT
    # Daily maintenance: 4:00-5:00 PM CT
    DAILY_SETTLE_MINUTE = 55  # Flatten at :55 of the 3 PM CT hour (15:55)
    DAILY_SETTLE_HOUR = 15

    # Sandbox replay speed: candles per second
    SANDBOX_REPLAY_SPEED = 10.0

    # Tradovate reconnection settings
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_BASE_DELAY = 5  # seconds

    def __init__(
        self,
        mode: TradingMode = TradingMode.SANDBOX,
        broadcast_fn: Optional[Callable[..., Coroutine]] = None,
    ):
        self.config = get_config()
        self.mode = mode
        self._broadcast = broadcast_fn

        # Status tracking
        self.status = OrchestratorStatus.IDLE
        self.metrics = LoopMetrics()
        self._running = False
        self._current_day: Optional[str] = None

        # Components — orchestrator owns its own instances
        self.feature_engine = FeatureEngine()
        self.regime_detector = RegimeDetector()
        self.allocator = Allocator()
        self.risk_manager = RiskManager()
        self.exec_engine = ExecutionEngine(mode=mode)
        self.candle_store = CandleStore()
        self.contract_resolver = ContractResolver()
        self.state_persistence = OrchestratorState()
        self.event_bus = get_event_bus()

        # Tradovate client (created on connect for PAPER/LIVE)
        self._tradovate: Optional[TradovateClient] = None
        self._contract_symbol: str = ""

    # ── PUBLIC API ──────────────────────────────────────────────────────

    async def start(self):
        """Start the trading loop."""
        if self._running:
            logger.warning("Orchestrator already running")
            return

        self._running = True
        self.status = OrchestratorStatus.CONNECTING
        self.metrics = LoopMetrics(start_time=datetime.now().isoformat())

        # Resolve current MES contract
        self._contract_symbol = self.contract_resolver.get_front_month()
        logger.info(f"Front-month contract: {self._contract_symbol}")

        # Load persisted state
        self._load_persisted_state()

        logger.info(
            f"Orchestrator starting in {self.mode.value} mode "
            f"(contract={self._contract_symbol})"
        )

        try:
            if self.mode == TradingMode.SANDBOX:
                await self._run_sandbox_loop()
            else:
                await self._run_live_loop()
        except asyncio.CancelledError:
            logger.info("Orchestrator task cancelled")
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            self.metrics.last_error = str(e)
        finally:
            self.status = OrchestratorStatus.IDLE
            self._running = False
            self._save_state()
            logger.info("Orchestrator stopped")

    async def stop(self):
        """Stop the trading loop gracefully."""
        logger.info("Orchestrator stopping...")
        self.status = OrchestratorStatus.SHUTDOWN
        self._running = False

        # Flatten any open position
        account = self.exec_engine.get_account_state()
        if account.open_position:
            latest = self.candle_store.get_latest_candle()
            if latest:
                self.exec_engine.flatten_all(
                    latest.close, latest.ts, "Orchestrator shutdown"
                )
                await self._publish_event(EventType.POSITION_CLOSED, {
                    "reason": "orchestrator_shutdown",
                })

        # Disconnect Tradovate
        if self._tradovate:
            await self._tradovate.market_data.disconnect()

        # Save final state
        self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status and metrics for API."""
        account = self.exec_engine.get_account_state()
        return {
            "status": self.status.value,
            "mode": self.mode.value,
            "contract": self._contract_symbol,
            "account": {
                "balance": round(account.balance, 2),
                "daily_pnl": round(account.daily_pnl, 2),
                "daily_trades": account.daily_trades,
                "consecutive_losses": account.consecutive_losses,
                "has_position": account.open_position is not None,
                "should_halt": account.should_halt,
            },
            "metrics": {
                "candles_processed": self.metrics.candles_processed,
                "signals_generated": self.metrics.signals_generated,
                "orders_submitted": self.metrics.orders_submitted,
                "orders_filled": self.metrics.orders_filled,
                "orders_rejected": self.metrics.orders_rejected,
                "positions_opened": self.metrics.positions_opened,
                "positions_closed": self.metrics.positions_closed,
                "last_candle_ts": self.metrics.last_candle_ts,
                "last_error": self.metrics.last_error,
                "start_time": self.metrics.start_time,
            },
        }

    # ── SANDBOX LOOP ────────────────────────────────────────────────────

    async def _run_sandbox_loop(self):
        """Replay stored candles from CandleStore at configurable speed."""
        self.status = OrchestratorStatus.RUNNING
        logger.info("Starting sandbox replay loop")

        candles_df = self.candle_store.get_candles(
            symbol="MES", timeframe="5min", limit=5000
        )

        if candles_df.empty:
            logger.error("No candle data for sandbox replay")
            return

        # Need at least 60 bars for features
        start_idx = 60
        total = len(candles_df)

        await self._broadcast_update("system", {
            "message": f"Sandbox replay started: {total - start_idx} candles",
            "mode": "sandbox",
        })

        for i in range(start_idx, total):
            if not self._running:
                break

            # Build a Candle from the DataFrame row
            row = candles_df.iloc[i]
            candle = Candle(
                symbol=row.get("symbol", "MES"),
                timeframe=row.get("timeframe", "5min"),
                ts=pd.Timestamp(row["ts"]).to_pydatetime()
                if not isinstance(row["ts"], datetime) else row["ts"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0)),
            )

            # Get lookback window
            lookback_df = candles_df.iloc[max(0, i - 300):i + 1].copy()

            await self._process_candle(candle, lookback_df)

            # Throttle replay speed
            await asyncio.sleep(1.0 / self.SANDBOX_REPLAY_SPEED)

        logger.info(f"Sandbox replay complete: {self.metrics.candles_processed} candles")
        await self._broadcast_update("system", {
            "message": "Sandbox replay complete",
            "candles_processed": self.metrics.candles_processed,
            "trades": self.metrics.positions_opened,
        })

    # ── LIVE/PAPER LOOP ─────────────────────────────────────────────────

    async def _run_live_loop(self):
        """Connect to Tradovate WebSocket and process real-time bars."""
        self.status = OrchestratorStatus.CONNECTING

        # Create Tradovate client
        self._tradovate = TradovateClient(TradovateConfig.from_env())

        reconnect_attempts = 0

        while self._running and reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS:
            try:
                # Authenticate
                logger.info("Authenticating with Tradovate...")
                await self._tradovate.connect()

                # Verify contract
                verified = await self.contract_resolver.verify_contract(
                    self._contract_symbol, self._tradovate.rest
                )
                if not verified:
                    logger.warning(
                        f"Contract {self._contract_symbol} not verified, "
                        "continuing anyway..."
                    )

                # Register callbacks
                self._tradovate.market_data.on("chart", self._on_tradovate_chart)
                self._tradovate.market_data.on("quote", self._on_tradovate_quote)

                self.status = OrchestratorStatus.RUNNING
                reconnect_attempts = 0  # Reset on successful connection

                await self._broadcast_update("system", {
                    "message": f"Connected to Tradovate ({self.mode.value})",
                    "contract": self._contract_symbol,
                })

                # Start WebSocket in a task, subscribe, then wait
                ws_task = asyncio.create_task(
                    self._tradovate.market_data.connect()
                )

                # Wait briefly for WebSocket connection, then subscribe
                await asyncio.sleep(2)
                await self._tradovate.market_data.subscribe_chart(
                    self._contract_symbol, "5min"
                )
                await self._tradovate.market_data.subscribe_quotes(
                    self._contract_symbol
                )

                logger.info(
                    f"Subscribed to {self._contract_symbol} 5min chart + quotes"
                )

                # Main heartbeat loop — WebSocket processes messages in ws_task
                while self._running:
                    if ws_task.done():
                        exc = ws_task.exception()
                        if exc:
                            raise exc
                        break  # WebSocket disconnected, reconnect

                    await asyncio.sleep(1)
                    await self._daily_checks()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                reconnect_attempts += 1
                logger.error(
                    f"Tradovate connection error "
                    f"(attempt {reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS}): {e}"
                )
                self.metrics.last_error = str(e)

                if self._running:
                    delay = min(
                        self.RECONNECT_BASE_DELAY * (2 ** reconnect_attempts),
                        300,
                    )
                    logger.info(f"Reconnecting in {delay}s...")
                    await asyncio.sleep(delay)

        if reconnect_attempts >= self.MAX_RECONNECT_ATTEMPTS:
            logger.error("Max reconnection attempts reached. Stopping.")
            await self._broadcast_update("system", {
                "message": "Tradovate connection failed — max retries exceeded",
                "error": self.metrics.last_error,
            })

    # ── TRADOVATE CALLBACKS ─────────────────────────────────────────────

    async def _on_tradovate_chart(self, data: dict):
        """Handle chart data from Tradovate WebSocket.

        Tradovate chart data format:
        {
            "charts": [{
                "bars": [{
                    "timestamp": "2026-03-09T...",
                    "open": 5847.50, "high": 5850.00,
                    "low": 5845.25, "close": 5848.75,
                    "upVolume": 1234, "downVolume": 987,
                    "upTicks": 50, "downTicks": 40
                }]
            }]
        }
        """
        try:
            charts = data.get("charts", [])
            for chart in charts:
                bars = chart.get("bars", [])
                if not bars:
                    continue

                # Process the most recent completed bar
                bar = bars[-1]
                candle = self._tradovate_bar_to_candle(bar)

                if candle:
                    # Store in DuckDB
                    self.candle_store.insert_candles([candle])

                    # Get lookback window
                    candles_df = self.candle_store.get_candles(
                        symbol="MES", timeframe="5min", limit=300
                    )

                    await self._process_candle(candle, candles_df)

        except Exception as e:
            logger.error(f"Error processing chart data: {e}", exc_info=True)

    def _tradovate_bar_to_candle(self, bar: dict) -> Optional[Candle]:
        """Convert a Tradovate bar dict to internal Candle type."""
        try:
            ts_str = bar.get("timestamp", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                ts = datetime.now()

            up_vol = bar.get("upVolume", 0) or 0
            down_vol = bar.get("downVolume", 0) or 0

            return Candle(
                symbol="MES",
                timeframe="5min",
                ts=ts,
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(up_vol + down_vol),
                buy_volume=float(up_vol),
                sell_volume=float(down_vol),
                delta=float(up_vol - down_vol),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to convert Tradovate bar: {e}")
            return None

    async def _on_tradovate_quote(self, data: dict):
        """Handle real-time quote data (logged for observability)."""
        # Future enhancement: intra-bar SL/TP checking using tick-level data
        pass

    # ── CORE PIPELINE ───────────────────────────────────────────────────

    async def _process_candle(self, candle: Candle, candles_df: pd.DataFrame):
        """The core trading pipeline, executed on every candle close.

        This mirrors the backtester logic from backtester/engine.py (lines 171-317)
        but runs asynchronously with event publishing and UI broadcasting.
        """
        self.metrics.candles_processed += 1
        ts_str = (
            candle.ts.isoformat()
            if isinstance(candle.ts, datetime) else str(candle.ts)
        )
        self.metrics.last_candle_ts = ts_str

        # ── 1. Daily Reset ────────────────────────────────────────────
        day = ts_str[:10]
        if day != self._current_day:
            if self._current_day is not None:
                # Save previous day's summary
                account = self.exec_engine.get_account_state()
                self.state_persistence.save_daily_summary(
                    self._current_day,
                    account.daily_pnl,
                    account.daily_trades,
                    account.daily_wins,
                    account.daily_losses,
                )
            self._current_day = day
            self.risk_manager.reset_daily()
            await self._publish_event(EventType.SESSION_START, {"date": day})

        # ── 2. Check existing position (SL/TP + daily reset) ──────────
        closed_trade = self.exec_engine.process_candle(candle)
        if closed_trade:
            self.metrics.positions_closed += 1
            self.risk_manager.record_trade_result(closed_trade.pnl)
            await self._publish_event(EventType.POSITION_CLOSED, {
                "trade_id": closed_trade.id,
                "pnl": closed_trade.pnl,
                "direction": closed_trade.direction.value,
                "exit_price": closed_trade.exit_price,
            })
            await self._broadcast_trade_close(closed_trade)

        # ── 3. Check halt conditions ──────────────────────────────────
        account = self.exec_engine.get_account_state()
        if account.should_halt:
            await self._broadcast_update("halt", {
                "reason": "Daily limits reached",
                "pdll_hit": account.is_pdll_hit,
                "pdpt_hit": account.is_pdpt_hit,
                "max_trades_hit": account.is_max_trades_hit,
                "daily_pnl": round(account.daily_pnl, 2),
            })
            return

        # ── 4. Session close check (no overnight — TopstepX rule) ─────
        if self._is_near_close(candle.ts):
            if account.open_position:
                self.exec_engine.flatten_all(
                    candle.close, candle.ts, "End of session flatten"
                )
                self.metrics.positions_closed += 1
                await self._publish_event(EventType.POSITION_CLOSED, {
                    "reason": "eod_flatten",
                })
            return

        # ── 5. Skip if position already open ──────────────────────────
        if account.open_position is not None:
            await self._broadcast_position_update(candle)
            return

        # ── 6. Compute features ──────────────────────────────────────
        if len(candles_df) < 60:
            return  # Not enough data for feature computation

        try:
            features_full = self.feature_engine.compute(candles_df)
            fv = self.feature_engine.compute_feature_vector(candles_df, -1)
        except Exception as e:
            logger.error(f"Feature computation error: {e}")
            return

        # ── 7. Detect regime ─────────────────────────────────────────
        regime = Regime.UNKNOWN
        regime_confidence = 0.0
        try:
            if not features_full.empty and len(features_full) > 30:
                self.regime_detector.fit(features_full)
                regime, regime_confidence = self.regime_detector.predict_current(
                    features_full
                )
                fv.regime = regime
                fv.regime_confidence = regime_confidence
        except Exception as e:
            logger.warning(f"Regime detection error: {e}")

        await self._publish_event(EventType.FEATURES_UPDATED, {
            "ts": ts_str,
            "regime": regime.value,
            "regime_confidence": round(regime_confidence, 4),
            "atr_14": round(fv.atr_14, 4),
            "rsi_14": round(fv.rsi_14, 2),
        })

        # ── 8. Collect signals from all active agents ────────────────
        agents = get_all_agents()
        signals: List[Signal] = []

        for agent in agents:
            if not agent.should_be_active(regime):
                continue
            try:
                signal = agent.on_features(fv, candles_df)
                if signal:
                    signals.append(signal)
                    self.metrics.signals_generated += 1
                    await self._publish_event(EventType.AGENT_SIGNAL, {
                        "agent_id": agent.agent_id,
                        "direction": signal.direction.value,
                        "confidence": round(signal.confidence, 4),
                        "entry": signal.entry_price,
                        "stop": signal.stop_loss,
                        "target": signal.take_profit,
                        "rr": signal.risk_reward_ratio,
                    })
            except Exception as e:
                logger.error(f"Agent {agent.agent_id} error: {e}")

        if not signals:
            await self._broadcast_update("tick", {
                "ts": ts_str,
                "close": candle.close,
                "regime": regime.value,
                "signals": 0,
                "balance": round(account.balance, 2),
            })
            return

        # ── 9. Combine signals via allocator ─────────────────────────
        combined = self.allocator.combine_signals(signals, regime)
        if combined is None:
            await self._broadcast_update("tick", {
                "ts": ts_str,
                "close": candle.close,
                "regime": regime.value,
                "signals": len(signals),
                "combined": None,
                "reason": "Allocator filtered or conflicting signals",
            })
            return

        await self._publish_event(EventType.COMBINED_SIGNAL, {
            "direction": combined.direction.value,
            "confidence": round(combined.confidence, 4),
            "agents": combined.contributing_agents,
            "reasoning": combined.reasoning,
        })

        # ── 10. Risk evaluation ──────────────────────────────────────
        current_time = (
            candle.ts if isinstance(candle.ts, datetime) else datetime.now()
        )
        decision = self.risk_manager.evaluate(
            signal=combined,
            account=account,
            current_regime=regime,
            current_time=current_time,
            minutes_to_news=fv.minutes_to_news,
        )

        if not decision.approved:
            self.metrics.orders_rejected += 1
            await self._publish_event(EventType.ORDER_REJECTED, {
                "reason": decision.rejection_reason,
                "direction": combined.direction.value,
                "confidence": round(combined.confidence, 4),
            })
            await self._broadcast_update("rejected", {
                "ts": ts_str,
                "reason": decision.rejection_reason,
            })
            return

        # ── 11. Execute order ─────────────────────────────────────────
        order = decision.order
        self.metrics.orders_submitted += 1

        await self._publish_event(EventType.ORDER_SUBMITTED, {
            "order_id": order.id,
            "direction": order.direction.value,
            "price": order.price,
            "quantity": order.quantity,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
        })

        # Use async path for LIVE, sync for SANDBOX/PAPER
        if self.mode == TradingMode.LIVE and self._tradovate:
            fill = await self.exec_engine.async_submit_order(
                order, candle, self._tradovate, self._contract_symbol
            )
        else:
            fill = self.exec_engine.submit_order(order, candle)

        if fill.filled:
            trade = self.exec_engine.open_position(order, fill, candle.ts)
            self.metrics.orders_filled += 1
            self.metrics.positions_opened += 1

            await self._publish_event(EventType.ORDER_FILLED, {
                "order_id": order.id,
                "fill_price": fill.fill_price,
                "slippage": fill.slippage_ticks,
            })
            await self._publish_event(EventType.POSITION_OPENED, {
                "trade_id": trade.id,
                "direction": trade.direction.value,
                "entry": trade.entry_price,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "agents": trade.agent_signals_used,
                "confidence": round(combined.confidence, 4),
            })

            await self._broadcast_update("trade_opened", {
                "trade_id": trade.id,
                "direction": trade.direction.value,
                "entry": trade.entry_price,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "confidence": round(combined.confidence, 4),
                "agents": combined.contributing_agents,
                "warnings": decision.warnings,
                "regime": regime.value,
            })
        else:
            logger.warning(f"Order not filled: {fill.reason}")
            await self._broadcast_update("tick", {
                "ts": ts_str,
                "close": candle.close,
                "order_not_filled": fill.reason,
            })

        # ── 12. Persist state ─────────────────────────────────────────
        self._save_state()

    # ── HELPER METHODS ──────────────────────────────────────────────────

    def _is_near_close(self, ts: Any) -> bool:
        """Check if we're within the settlement window.

        MES daily settlement at 4:00 PM CT. We flatten at 3:55 PM CT.
        TopstepX requires no overnight positions.

        Note: Assumes candle timestamps are in CT (Central Time).
        For production, should use proper timezone handling.
        """
        if not isinstance(ts, datetime):
            return False

        h, m = ts.hour, ts.minute
        # 3:55 PM to 4:59 PM CT → flatten zone
        if h == self.DAILY_SETTLE_HOUR and m >= self.DAILY_SETTLE_MINUTE:
            return True
        if h == 16:
            return True
        return False

    async def _daily_checks(self):
        """Periodic checks: contract rollover, session boundaries."""
        now = datetime.now()

        # Check for contract rollover (daily)
        new_contract = self.contract_resolver.get_front_month(now.date())
        if new_contract != self._contract_symbol:
            logger.info(
                f"Contract rollover: {self._contract_symbol} → {new_contract}"
            )
            self._contract_symbol = new_contract
            # Future: re-subscribe with new contract symbol

    def _load_persisted_state(self):
        """Load state from SQLite on startup."""
        saved_account = self.state_persistence.load_account_state()
        if saved_account is None:
            logger.info("No persisted state found, starting fresh")
            return

        meta = self.state_persistence.load_orchestrator_meta()
        today = datetime.now().strftime("%Y-%m-%d")

        if meta and meta.get("last_trading_day") == today:
            # Same day: restore all state including daily counters
            self.exec_engine.account = saved_account
            self._current_day = today
            logger.info(
                f"Restored same-day state: balance=${saved_account.balance:.2f}, "
                f"daily_pnl=${saved_account.daily_pnl:.2f}"
            )
        else:
            # New day: restore balance/peak but reset daily counters
            self.exec_engine.account.balance = saved_account.balance
            self.exec_engine.account.peak_balance = saved_account.peak_balance
            self.exec_engine.account.initial_balance = saved_account.initial_balance
            logger.info(
                f"New trading day. Restored balance=${saved_account.balance:.2f}"
            )

    def _save_state(self):
        """Persist current state to SQLite."""
        account = self.exec_engine.get_account_state()
        self.state_persistence.save_account_state(account)
        self.state_persistence.save_orchestrator_meta(
            mode=self.mode,
            contract_symbol=self._contract_symbol,
            last_trading_day=self._current_day
            or datetime.now().strftime("%Y-%m-%d"),
        )

    # ── EVENT & BROADCAST HELPERS ───────────────────────────────────────

    async def _publish_event(self, event_type: EventType, data: dict):
        """Publish event to EventBus and broadcast to UI."""
        event = Event(type=event_type, data=data, source="orchestrator")
        await self.event_bus.publish(event)

        # Also broadcast to WebSocket clients
        if self._broadcast:
            try:
                await self._broadcast({"type": event_type.value, **data})
            except Exception as e:
                logger.debug(f"Broadcast error: {e}")

    async def _broadcast_update(self, update_type: str, data: dict):
        """Broadcast a UI update via WebSocket."""
        if self._broadcast:
            try:
                await self._broadcast({"type": update_type, **data})
            except Exception:
                pass

    async def _broadcast_trade_close(self, trade: Trade):
        """Broadcast trade close event with full details."""
        await self._broadcast_update("trade_closed", {
            "trade_id": trade.id,
            "direction": trade.direction.value,
            "entry": trade.entry_price,
            "exit": trade.exit_price,
            "pnl": trade.pnl,
            "pnl_ticks": trade.pnl_ticks,
            "balance": round(
                self.exec_engine.get_account_state().balance, 2
            ),
        })

    async def _broadcast_position_update(self, candle: Candle):
        """Broadcast unrealized PnL update for open position."""
        pos = self.exec_engine.get_account_state().open_position
        if pos:
            if pos.direction == Direction.LONG:
                unrealized = (candle.close - pos.entry_price) * 5.0 * pos.quantity
            else:
                unrealized = (pos.entry_price - candle.close) * 5.0 * pos.quantity

            await self._broadcast_update("position_update", {
                "trade_id": pos.id,
                "direction": pos.direction.value,
                "entry": pos.entry_price,
                "current": candle.close,
                "unrealized_pnl": round(unrealized, 2),
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            })
