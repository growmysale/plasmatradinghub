"""PropEdge v2 - Full System Verification Script."""
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=== PropEdge v2 Full System Check ===")
print()

# Core
from core.types import Direction, Regime, TradingMode, Signal, Trade, AccountState
from core.config import get_config
from core.events import EventBus, EventType
print("[OK] Core: types, config, events")

# Data Engine
from data_engine.database import get_duckdb, get_sqlite
from data_engine.candle_store import CandleStore
from data_engine.tradovate import TradovateClient
print("[OK] Data Engine: database, candle_store, tradovate")

# Data Providers
from data_engine.providers.databento_provider import DatabentoProvider
from data_engine.providers.fred_provider import FREDProvider
from data_engine.providers.finnhub_provider import FinnhubProvider
from data_engine.providers.cot_provider import COTProvider
print("[OK] Data Providers: databento, fred, finnhub, cot")

# Feature Engine
from feature_engine.indicators import ema, rsi, atr, adx, vwap_with_bands
from feature_engine.engine import FeatureEngine
from feature_engine.regime import RegimeDetector
print("[OK] Feature Engine: indicators (80), regime detector (HMM)")

# Agents
from agents.base import StrategyAgent
from agents.registry import get_all_agents, AGENT_CLASSES
print(f"[OK] Agents: {len(AGENT_CLASSES)} registered")

# Backtester
from backtester.engine import BacktestEngine, BacktestResult
print("[OK] Backtester: walk-forward, Monte Carlo, significance")

# Allocator
from allocator.meta_strategy import Allocator
print("[OK] Allocator: weighted_vote, regime_conditional, unanimous")

# Risk Manager
from risk_manager.governor import RiskManager
print("[OK] Risk Manager: 6-stage pipeline, circuit breakers, Kelly")

# Execution
from execution.sandbox import ExecutionEngine
print("[OK] Execution: sandbox/paper/live modes")

# Evolution
from evolution.genetic import EvolutionEngine, Individual
print("[OK] Evolution: genetic strategy optimization")

# API
from api.main import app
print("[OK] API: FastAPI REST + WebSocket")

# Config
config = get_config()
print()
print("=== Configuration ===")
print(f"Prop Firm: {config.prop_firm.name} (${config.prop_firm.initial_balance:,.0f})")
print(f"PDLL: ${config.personal_risk.pdll} | PDPT: ${config.personal_risk.pdpt}")
print(f"Max Trades/Day: {config.personal_risk.max_trades_per_day}")
print(f"Max Risk/Trade: ${config.personal_risk.max_risk_per_trade}")
print(f"Execution Mode: {config.execution.mode}")

# Data
store = CandleStore()
print(f"Candles Loaded: {store.get_candle_count()}")

print()
print("=== SYSTEM READY ===")
