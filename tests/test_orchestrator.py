"""Test the orchestrator package: contract resolver, state persistence, and trading loop."""
import pytest
from datetime import date, datetime


# ── Contract Resolver Tests ───────────────────────────────────────────────

def test_contract_resolver_front_month():
    """Test front-month resolution for various dates."""
    from orchestrator.contract_resolver import ContractResolver

    resolver = ContractResolver(rollover_days_before_expiry=8)

    # March 2026: before rollover (third Friday is ~March 20)
    # rollover_date = March 20 - 8 = March 12
    symbol = resolver.get_front_month(date(2026, 3, 9))
    assert symbol == "MESH6", f"Expected MESH6, got {symbol}"

    # March 2026: after rollover → June contract
    symbol = resolver.get_front_month(date(2026, 3, 15))
    assert symbol == "MESM6", f"Expected MESM6, got {symbol}"

    # June 2026: before rollover
    symbol = resolver.get_front_month(date(2026, 5, 1))
    assert symbol == "MESM6", f"Expected MESM6, got {symbol}"

    # September 2026: before rollover
    symbol = resolver.get_front_month(date(2026, 8, 1))
    assert symbol == "MESU6", f"Expected MESU6, got {symbol}"

    # December 2026: before rollover
    symbol = resolver.get_front_month(date(2026, 11, 1))
    assert symbol == "MESZ6", f"Expected MESZ6, got {symbol}"


def test_contract_resolver_year_boundary():
    """Test contract resolution across year boundaries."""
    from orchestrator.contract_resolver import ContractResolver

    resolver = ContractResolver(rollover_days_before_expiry=8)

    # After December rollover → next year's March contract
    symbol = resolver.get_front_month(date(2026, 12, 20))
    assert symbol == "MESH7", f"Expected MESH7, got {symbol}"


def test_third_friday():
    """Test third Friday computation."""
    from orchestrator.contract_resolver import ContractResolver

    resolver = ContractResolver()

    # March 2026: third Friday should be March 20
    friday = resolver._third_friday(2026, 3)
    assert friday.weekday() == 4  # Friday
    assert friday.month == 3
    assert friday.day >= 15 and friday.day <= 21


def test_rollover_date():
    """Test rollover date computation."""
    from orchestrator.contract_resolver import ContractResolver

    resolver = ContractResolver(rollover_days_before_expiry=8)
    rollover = resolver.get_rollover_date(date(2026, 3, 1))
    assert rollover.month == 3
    assert rollover > date(2026, 3, 1)


# ── State Persistence Tests ──────────────────────────────────────────────

def test_state_save_and_load():
    """Test saving and loading account state."""
    from orchestrator.state import OrchestratorState
    from core.types import AccountState, TradingMode

    state = OrchestratorState()

    account = AccountState(
        balance=51250.00,
        initial_balance=50000.00,
        peak_balance=51500.00,
        daily_pnl=125.50,
        daily_trades=2,
        daily_wins=1,
        daily_losses=1,
        consecutive_losses=0,
        mode=TradingMode.SANDBOX,
    )

    state.save_account_state(account)
    loaded = state.load_account_state()

    assert loaded is not None
    assert loaded.balance == 51250.00
    assert loaded.peak_balance == 51500.00
    assert loaded.daily_pnl == 125.50
    assert loaded.daily_trades == 2
    assert loaded.mode == TradingMode.SANDBOX


def test_orchestrator_meta():
    """Test saving and loading orchestrator metadata."""
    from orchestrator.state import OrchestratorState
    from core.types import TradingMode

    state = OrchestratorState()

    state.save_orchestrator_meta(
        mode=TradingMode.PAPER,
        contract_symbol="MESH6",
        last_trading_day="2026-03-09",
    )

    meta = state.load_orchestrator_meta()
    assert meta is not None
    assert meta["mode"] == "paper"
    assert meta["contract_symbol"] == "MESH6"
    assert meta["last_trading_day"] == "2026-03-09"


def test_daily_summary():
    """Test saving and loading daily summaries."""
    from orchestrator.state import OrchestratorState

    state = OrchestratorState()

    state.save_daily_summary(
        date_str="2026-03-09",
        pnl=175.50,
        trades=3,
        wins=2,
        losses=1,
    )

    summary = state.get_daily_summary("2026-03-09")
    assert summary is not None
    assert summary["pnl"] == 175.50
    assert summary["trades"] == 3
    assert summary["wins"] == 2


# ── Trading Loop Tests ────────────────────────────────────────────────────

def test_orchestrator_creation():
    """Test TradingOrchestrator can be created."""
    from orchestrator.trading_loop import TradingOrchestrator, OrchestratorStatus
    from core.types import TradingMode

    orch = TradingOrchestrator(mode=TradingMode.SANDBOX)
    assert orch.status == OrchestratorStatus.IDLE
    assert orch.mode == TradingMode.SANDBOX
    assert orch._contract_symbol == ""


def test_orchestrator_status():
    """Test get_status returns proper structure."""
    from orchestrator.trading_loop import TradingOrchestrator
    from core.types import TradingMode

    orch = TradingOrchestrator(mode=TradingMode.SANDBOX)
    status = orch.get_status()

    assert "status" in status
    assert "mode" in status
    assert "account" in status
    assert "metrics" in status
    assert status["status"] == "idle"
    assert status["mode"] == "sandbox"
    assert "balance" in status["account"]
    assert "candles_processed" in status["metrics"]


def test_tradovate_bar_conversion():
    """Test conversion of Tradovate bar dict to Candle."""
    from orchestrator.trading_loop import TradingOrchestrator
    from core.types import TradingMode

    orch = TradingOrchestrator(mode=TradingMode.SANDBOX)

    bar = {
        "timestamp": "2026-03-09T10:30:00Z",
        "open": 5847.50,
        "high": 5850.00,
        "low": 5845.25,
        "close": 5848.75,
        "upVolume": 1234,
        "downVolume": 987,
        "upTicks": 50,
        "downTicks": 40,
    }

    candle = orch._tradovate_bar_to_candle(bar)
    assert candle is not None
    assert candle.symbol == "MES"
    assert candle.open == 5847.50
    assert candle.close == 5848.75
    assert candle.volume == 1234 + 987
    assert candle.delta == 1234 - 987


def test_is_near_close():
    """Test session close detection."""
    from orchestrator.trading_loop import TradingOrchestrator
    from core.types import TradingMode

    orch = TradingOrchestrator(mode=TradingMode.SANDBOX)

    # 3:55 PM → should flatten
    assert orch._is_near_close(datetime(2026, 3, 9, 15, 55)) is True

    # 4:00 PM → should flatten
    assert orch._is_near_close(datetime(2026, 3, 9, 16, 0)) is True

    # 3:30 PM → still trading
    assert orch._is_near_close(datetime(2026, 3, 9, 15, 30)) is False

    # 10:00 AM → still trading
    assert orch._is_near_close(datetime(2026, 3, 9, 10, 0)) is False


# ── API Endpoint Tests ────────────────────────────────────────────────────

def test_trading_status_endpoint():
    """Test the /api/trading/status endpoint returns data."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get("/api/trading/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] == "idle"
