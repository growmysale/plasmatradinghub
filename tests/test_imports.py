"""Test that all modules import cleanly.

This is the first gate in the CI pipeline — if any module
has a syntax error, missing dependency, or broken import,
it fails here before we ever deploy.
"""
import pytest


def test_core_imports():
    from core.config import get_config, PropEdgeConfig
    from core.types import Candle, Signal, Trade
    from core.events import EventBus


def test_data_engine_imports():
    from data_engine.database import DuckDBManager, SQLiteManager, get_duckdb, get_sqlite
    from data_engine.candle_store import CandleStore


def test_data_providers_imports():
    from data_engine.providers.fred_provider import FREDProvider
    from data_engine.providers.finnhub_provider import FinnhubProvider
    from data_engine.providers.cot_provider import COTProvider


def test_feature_engine_imports():
    from feature_engine.engine import FeatureEngine
    from feature_engine.indicators import rsi, ema, atr, vwap_with_bands
    from feature_engine.regime import RegimeDetector


def test_agents_imports():
    from agents.registry import AGENT_CLASSES
    from agents.base import StrategyAgent
    assert len(AGENT_CLASSES) >= 5, f"Expected at least 5 agents, got {len(AGENT_CLASSES)}"


def test_backtester_imports():
    from backtester.engine import BacktestEngine


def test_allocator_imports():
    from allocator.meta_strategy import Allocator


def test_risk_manager_imports():
    from risk_manager.governor import RiskManager


def test_execution_imports():
    from execution.sandbox import ExecutionEngine


def test_evolution_imports():
    from evolution.genetic import EvolutionEngine


def test_api_imports():
    from api.main import app
