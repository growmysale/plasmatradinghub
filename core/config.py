"""PropEdge Configuration System.

YAML-based configuration with sensible defaults.
All prop firm rules are hard-coded as non-negotiable limits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "configs"


@dataclass
class PropFirmConfig:
    """TopstepX $50K Combine rules - NON-NEGOTIABLE."""
    name: str = "TopstepX $50K"
    initial_balance: float = 50000.0
    max_loss_limit: float = 2000.0      # Trailing drawdown
    profit_target: float = 3000.0       # To pass combine
    consistency_rule: float = 0.5       # Best day < 50% of total profit
    no_overnight: bool = True           # Must be flat at close
    commission_free: bool = True        # TopstepX = no commissions
    scaling_plan: Dict[str, int] = field(default_factory=lambda: {
        "0": 2,       # Start: 2 contracts (20 MES)
        "1500": 3,    # Above $1,500 profit: 3 contracts
        "2000": 5,    # Above $2,000 profit: 5 contracts
    })


@dataclass
class PersonalRiskConfig:
    """Raymond's personal risk rules."""
    pdll: float = 200.0           # Personal Daily Loss Limit
    pdpt: float = 300.0           # Personal Daily Profit Target
    max_trades_per_day: int = 3
    max_risk_per_trade: float = 50.0  # $ risk per trade
    min_risk_reward: float = 2.0      # Minimum R:R ratio
    cooldown_after_consecutive_losses: int = 2   # Pause after N losses
    cooldown_minutes: int = 15
    halt_after_daily_losses: int = 3  # Stop after N losses in a day
    news_blackout_minutes: int = 5    # No trades within N min of news


@dataclass
class DataConfig:
    """Data infrastructure configuration."""
    duckdb_path: str = str(DATA_DIR / "propedge_analytics.duckdb")
    sqlite_path: str = str(DATA_DIR / "propedge_operational.db")
    historical_dir: str = str(DATA_DIR / "historical")
    models_dir: str = str(DATA_DIR / "models")
    features_dir: str = str(DATA_DIR / "features")
    default_symbol: str = "MES"
    default_timeframe: str = "5min"
    supported_timeframes: List[str] = field(
        default_factory=lambda: ["1min", "5min", "15min", "1hour", "1day"]
    )


@dataclass
class FeatureConfig:
    """Feature engine configuration."""
    window_size: int = 60           # Lookback bars for features
    ema_periods: List[int] = field(default_factory=lambda: [8, 20, 50])
    rsi_periods: List[int] = field(default_factory=lambda: [7, 14])
    atr_period: int = 14
    adx_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    vwap_std_bands: List[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])
    swing_lookback: int = 5         # Bars left/right for swing detection
    regime_retrain_days: int = 30   # Retrain HMM monthly


@dataclass
class AgentConfig:
    """Strategy agent configuration."""
    max_active_agents: int = 8
    min_confidence_threshold: float = 0.55
    signal_expiry_bars: int = 3
    paper_test_days: int = 30       # Min days in paper before live


@dataclass
class AllocatorConfig:
    """Meta-strategy allocator configuration."""
    combination_method: str = "weighted_vote"  # weighted_vote, stacking, regime_conditional, unanimous
    min_combined_confidence: float = 0.60
    unanimous_min_agents: int = 3
    weight_update_window: int = 20    # Rolling days for weight calc
    conflict_threshold: float = 0.15  # Max diff between opposing signals


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    slippage_ticks: float = 0.5       # Average slippage per side
    commission_per_side: float = 0.0  # TopstepX = free
    walk_forward_train_days: int = 60
    walk_forward_test_days: int = 5
    min_trades_for_significance: int = 30
    significance_level: float = 0.05
    monte_carlo_runs: int = 1000


@dataclass
class EvolutionConfig:
    """Genetic strategy evolution configuration."""
    population_size: int = 50
    mutation_range: float = 0.20      # ±20% parameter mutation
    crossover_rate: float = 0.3
    survival_rate: float = 0.10       # Top 10% survive
    max_generations: int = 100
    promotion_threshold_trades: int = 20
    extinction_threshold_sharpe: float = 0.0
    extinction_consecutive_periods: int = 3


@dataclass
class ExecutionConfig:
    """Execution engine configuration."""
    mode: str = "sandbox"             # sandbox, paper, live
    replay_speed: float = 100.0       # Multiplier for sandbox replay
    live_confirmation_days: int = 14  # Human confirmation period
    live_size_reduction: float = 0.5  # 50% size for first month
    kill_switch_key: str = "F12"
    auto_shutdown_loss: float = 150.0 # Auto-stop before PDLL


@dataclass
class UIConfig:
    """Frontend configuration."""
    api_port: int = 8000
    ws_port: int = 8001
    frontend_port: int = 3000
    theme: str = "dark"


@dataclass
class PropEdgeConfig:
    """Master configuration."""
    prop_firm: PropFirmConfig = field(default_factory=PropFirmConfig)
    personal_risk: PersonalRiskConfig = field(default_factory=PersonalRiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    allocator: AllocatorConfig = field(default_factory=AllocatorConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def load_config(config_path: Optional[str] = None) -> PropEdgeConfig:
    """Load configuration from YAML file with defaults."""
    config = PropEdgeConfig()

    if config_path is None:
        config_path = str(CONFIG_DIR / "default.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        _merge_config(config, raw)

    # Ensure directories exist
    os.makedirs(config.data.historical_dir, exist_ok=True)
    os.makedirs(config.data.models_dir, exist_ok=True)
    os.makedirs(config.data.features_dir, exist_ok=True)
    os.makedirs(Path(config.data.duckdb_path).parent, exist_ok=True)

    return config


def _merge_config(config: Any, raw: dict):
    """Recursively merge YAML dict into dataclass."""
    for key, value in raw.items():
        if hasattr(config, key):
            attr = getattr(config, key)
            if hasattr(attr, '__dataclass_fields__') and isinstance(value, dict):
                _merge_config(attr, value)
            else:
                setattr(config, key, value)


# Singleton instance
_config: Optional[PropEdgeConfig] = None


def get_config() -> PropEdgeConfig:
    """Get or create the singleton config."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
