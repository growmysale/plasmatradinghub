"""PropEdge Core Types - Shared data structures across all layers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Regime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE_EXPANSION = "volatile_expansion"
    QUIET_COMPRESSION = "quiet_compression"
    UNKNOWN = "unknown"


class MarketStructure(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    TRANSITIONING = "transitioning"


class TradingMode(str, Enum):
    SANDBOX = "sandbox"       # Historical replay
    PAPER = "paper"           # Live data, simulated execution
    LIVE = "live"             # Real money


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class KillZone(str, Enum):
    NONE = "none"
    LONDON = "london"          # 2:00 - 5:00 AM ET
    NY_AM = "ny_am"            # 8:30 - 11:00 AM ET
    NY_PM = "ny_pm"            # 1:00 - 3:00 PM ET


class CircuitBreakerAction(str, Enum):
    FLATTEN = "flatten"
    HALT = "halt"


# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class Candle:
    """Single OHLCV candle."""
    symbol: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    tick_count: int = 0
    vwap: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    delta: float = 0.0


@dataclass
class FeatureVector:
    """Complete feature vector for a single bar."""
    symbol: str
    timeframe: str
    ts: datetime
    features: Dict[str, float] = field(default_factory=dict)

    # Key features accessible directly
    regime: Regime = Regime.UNKNOWN
    regime_confidence: float = 0.0
    market_structure: MarketStructure = MarketStructure.TRANSITIONING
    vwap_distance_atr: float = 0.0
    ema20_distance_atr: float = 0.0
    rsi_14: float = 50.0
    atr_14: float = 0.0
    volume_ratio: float = 1.0
    is_kill_zone: bool = False
    kill_zone_name: KillZone = KillZone.NONE
    minutes_to_news: int = 999

    def to_array(self) -> list:
        """Return features as ordered list for ML consumption."""
        return list(self.features.values())

    def to_dict(self) -> dict:
        """Return features as dictionary."""
        return {**self.features}


@dataclass
class Signal:
    """Trading signal from a strategy agent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    ts: datetime = field(default_factory=datetime.now)
    agent_id: str = ""
    agent_version: str = "1.0"
    symbol: str = "MES"
    direction: Direction = Direction.FLAT
    confidence: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward_ratio: float = 0.0
    reasoning: str = ""
    features_used: List[str] = field(default_factory=list)
    features_snapshot: Dict[str, float] = field(default_factory=dict)
    regime_at_signal: Regime = Regime.UNKNOWN


@dataclass
class CombinedSignal:
    """Combined signal from the Allocator."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    ts: datetime = field(default_factory=datetime.now)
    direction: Direction = Direction.FLAT
    confidence: float = 0.0
    contributing_agents: List[str] = field(default_factory=list)
    agent_signals: List[Signal] = field(default_factory=list)
    position_size: int = 1
    reasoning: str = ""
    regime: Regime = Regime.UNKNOWN


@dataclass
class Order:
    """Order to be executed."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    ts: datetime = field(default_factory=datetime.now)
    symbol: str = "MES"
    direction: Direction = Direction.FLAT
    order_type: OrderType = OrderType.MARKET
    price: float = 0.0
    quantity: int = 1
    stop_loss: float = 0.0
    take_profit: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    signal_id: str = ""
    agent_signals_used: List[str] = field(default_factory=list)
    combined_confidence: float = 0.0


@dataclass
class Trade:
    """Executed trade record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    ts_open: datetime = field(default_factory=datetime.now)
    ts_close: Optional[datetime] = None
    symbol: str = "MES"
    direction: Direction = Direction.FLAT
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 1
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_ticks: float = 0.0
    commission: float = 0.0
    slippage_ticks: float = 0.0

    # What generated this trade
    agent_signals_used: List[str] = field(default_factory=list)
    combined_confidence: float = 0.0
    position_size_reason: str = ""

    # Context
    regime: Regime = Regime.UNKNOWN
    market_structure: MarketStructure = MarketStructure.TRANSITIONING
    session: str = ""
    vwap_position: str = ""
    atr_at_entry: float = 0.0
    features_at_entry: Dict[str, float] = field(default_factory=dict)

    # Psychology
    manual_override: bool = False
    override_reason: str = ""
    emotion_tag: str = ""
    followed_system: bool = True

    # Prop firm tracking
    account_balance_before: float = 0.0
    account_balance_after: float = 0.0
    max_loss_limit_distance: float = 0.0
    daily_pnl_before: float = 0.0
    daily_pnl_after: float = 0.0

    # Execution quality
    intended_entry: float = 0.0
    actual_entry: float = 0.0
    entry_slippage: float = 0.0
    intended_exit: float = 0.0
    actual_exit: float = 0.0
    exit_slippage: float = 0.0

    mode: TradingMode = TradingMode.SANDBOX


@dataclass
class AccountState:
    """Current account state for risk management."""
    balance: float = 50000.0
    initial_balance: float = 50000.0
    peak_balance: float = 50000.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0
    open_position: Optional[Trade] = None
    max_loss_limit: float = 2000.0  # TopstepX trailing drawdown
    daily_loss_limit: float = 200.0  # Raymond's PDLL
    daily_profit_target: float = 300.0  # Raymond's PDPT
    max_trades_per_day: int = 3
    consecutive_losses: int = 0
    mode: TradingMode = TradingMode.SANDBOX

    @property
    def drawdown(self) -> float:
        return self.peak_balance - self.balance

    @property
    def drawdown_pct(self) -> float:
        return self.drawdown / self.peak_balance if self.peak_balance > 0 else 0

    @property
    def max_loss_floor(self) -> float:
        """The balance floor - cannot drop below this."""
        return max(self.peak_balance - self.max_loss_limit, self.initial_balance - self.max_loss_limit)

    @property
    def distance_to_max_loss(self) -> float:
        return self.balance - self.max_loss_floor

    @property
    def is_pdll_hit(self) -> bool:
        return self.daily_pnl <= -self.daily_loss_limit

    @property
    def is_pdpt_hit(self) -> bool:
        return self.daily_pnl >= self.daily_profit_target

    @property
    def is_max_trades_hit(self) -> bool:
        return self.daily_trades >= self.max_trades_per_day

    @property
    def should_halt(self) -> bool:
        return self.is_pdll_hit or self.is_pdpt_hit or self.is_max_trades_hit


@dataclass
class AgentStats:
    """Performance statistics for a strategy agent."""
    agent_id: str = ""
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    expectancy: float = 0.0
    current_weight: float = 0.0
    oos_sharpe: float = 0.0
    oos_profit_factor: float = 0.0
    is_active: bool = True
