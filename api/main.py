"""PropEdge FastAPI Backend - API layer for UI communication.

Provides REST endpoints and WebSocket connections for the React frontend.
Designed to run:
  - Locally for development (make dev)
  - On EC2 via Docker for production (make deploy)
  - Accessed by Tauri desktop app over HTTPS/WSS
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import get_config
from core.types import Direction, Regime, TradingMode
from data_engine.database import get_duckdb, get_sqlite
from data_engine.candle_store import CandleStore, generate_sample_data
from feature_engine.engine import FeatureEngine, get_all_feature_columns
from feature_engine.regime import RegimeDetector
from agents.registry import get_all_agents, get_agent, AGENT_CLASSES
from backtester.engine import BacktestEngine, compute_metrics
from allocator.meta_strategy import Allocator
from risk_manager.governor import RiskManager
from execution.sandbox import ExecutionEngine
from orchestrator.trading_loop import TradingOrchestrator, OrchestratorStatus
from evolution.genetic import EvolutionEngine
from data_engine.providers.yfinance_provider import YFinanceProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment
PROPEDGE_ENV = os.getenv("PROPEDGE_ENV", "development")


# ── Pydantic Models ──────────────────────────────────────────────────────

class OverviewStats(BaseModel):
    total_pnl: float = 0
    today_pnl: float = 0
    total_trades: int = 0
    today_trades: int = 0
    win_rate: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    account_balance: float = 50000
    pdll_used: float = 0
    pdpt_progress: float = 0
    max_loss_distance: float = 2000
    scaling_contracts: int = 2
    mode: str = "sandbox"
    current_regime: str = "unknown"
    regime_confidence: float = 0


class AgentStatus(BaseModel):
    agent_id: str
    agent_name: str
    is_active: bool = True
    preferred_regimes: List[str] = []
    weight: float = 0.0
    total_signals: int = 0
    total_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    sharpe: float = 0.0
    status: str = "active"


class BacktestRequest(BaseModel):
    agent_id: str
    days: int = 60
    walk_forward: bool = True
    train_days: int = 30
    test_days: int = 5


class BacktestResponse(BaseModel):
    agent_id: str
    oos_total_trades: int = 0
    oos_win_rate: float = 0.0
    oos_profit_factor: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_expectancy: float = 0.0
    wf_num_windows: int = 0
    wf_pct_profitable_windows: float = 0.0
    p_value: float = 1.0
    is_significant: bool = False
    mc_probability_of_ruin: float = 0.0
    equity_curve: List[float] = []


class TradeRecord(BaseModel):
    id: str
    ts_open: str
    ts_close: Optional[str] = None
    direction: str
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    agent_signals: List[str] = []
    regime: str = ""
    mode: str = "sandbox"


class DailyStats(BaseModel):
    date: str
    pnl: float
    trades: int
    wins: int
    losses: int
    regime: str = ""


class TradingStartRequest(BaseModel):
    mode: str = "sandbox"  # "sandbox", "paper", "live"


class TradingModeRequest(BaseModel):
    mode: str  # "sandbox", "paper", "live"


class EvolutionStartRequest(BaseModel):
    generations: int = 10
    agent_types: Optional[List[str]] = None  # None = all agents


class EvolutionResponse(BaseModel):
    generation: int = 0
    population_size: int = 0
    best_fitness: float = 0.0
    avg_fitness: float = 0.0
    worst_fitness: float = 0.0
    status: str = "idle"
    best_individuals: List[Dict[str, Any]] = []


class DataDownloadRequest(BaseModel):
    source: str = "yfinance"
    timeframe: str = "5min"
    days: Optional[int] = None


class BacktestAllResponse(BaseModel):
    results: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}


# ── App Setup ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    logger.info("PropEdge v2 API starting...")
    config = get_config()

    # Ensure sample data exists
    store = CandleStore()
    count = store.get_candle_count()
    if count == 0:
        logger.info("Generating sample data...")
        generate_sample_data(days=90)
        logger.info("Sample data generated")

    yield

    # Shutdown: stop orchestrator gracefully
    global _orchestrator
    if _orchestrator and _orchestrator.status != OrchestratorStatus.IDLE:
        logger.info("Stopping orchestrator on shutdown...")
        await _orchestrator.stop()

    logger.info("PropEdge v2 API shutting down")


app = FastAPI(
    title="PropEdge v2 - Adaptive Neural Trading System",
    description="Personal institutional-grade quant desk API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: Allow Tauri desktop app + local dev + any custom origin
allowed_origins = [
    "http://localhost:3000",       # Vite dev server
    "http://localhost:1420",       # Tauri dev server
    "http://127.0.0.1:3000",
    "http://127.0.0.1:1420",
    "https://tauri.localhost",     # Tauri production origin
    "tauri://localhost",           # Tauri custom protocol
]
# In development, allow all origins for convenience
if PROPEDGE_ENV == "development":
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton instances
_engine = FeatureEngine()
_regime = RegimeDetector()
_allocator = Allocator()
_risk_mgr = RiskManager()
_exec_engine = ExecutionEngine()
_ws_clients: List[WebSocket] = []

# Orchestrator state
_orchestrator: Optional[TradingOrchestrator] = None
_orchestrator_task: Optional[asyncio.Task] = None

# Evolution state
_evolution_engine: Optional[EvolutionEngine] = None
_evolution_task: Optional[asyncio.Task] = None
_evolution_status: str = "idle"  # idle, running, complete, error
_evolution_generations_target: int = 0
_evolution_results: List[Dict[str, Any]] = []


# ── REST Endpoints ───────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    config = get_config()
    store = CandleStore()
    return {
        "status": "running",
        "version": "2.0.0",
        "mode": config.execution.mode,
        "candles_loaded": store.get_candle_count(),
        "agents_available": len(AGENT_CLASSES),
        "features_count": len(get_all_feature_columns()),
    }


@app.get("/api/overview", response_model=OverviewStats)
async def get_overview():
    """Command Center overview stats."""
    config = get_config()
    account = _exec_engine.get_account_state()
    store = CandleStore()

    # Get current regime
    candles = store.get_candles(limit=500)
    regime_str = "unknown"
    regime_conf = 0.0
    if not candles.empty:
        features = _engine.compute(candles)
        if not features.empty:
            try:
                _regime.fit(features)
                regime, conf = _regime.predict_current(features)
                regime_str = regime.value
                regime_conf = conf
            except Exception:
                pass

    # Get trade stats
    trades = _exec_engine.get_trade_history()
    pnls = [t.pnl for t in trades if t.pnl is not None]
    metrics = compute_metrics(pnls) if pnls else {}

    # Today's stats
    today = datetime.now().date()
    today_trades = [t for t in trades if t.ts_open and t.ts_open.date() == today]
    today_pnl = sum(t.pnl for t in today_trades if t.pnl)

    # Scaling
    profit = account.balance - account.initial_balance
    contracts = 2
    for threshold, c in sorted(config.prop_firm.scaling_plan.items(), key=lambda x: float(x[0])):
        if profit >= float(threshold):
            contracts = c

    return OverviewStats(
        total_pnl=round(sum(pnls), 2) if pnls else 0,
        today_pnl=round(today_pnl, 2),
        total_trades=len(trades),
        today_trades=len(today_trades),
        win_rate=metrics.get("win_rate", 0),
        profit_factor=metrics.get("profit_factor", 0),
        max_drawdown=metrics.get("max_drawdown", 0),
        account_balance=round(account.balance, 2),
        pdll_used=round(abs(min(account.daily_pnl, 0)), 2),
        pdpt_progress=round(max(account.daily_pnl, 0), 2),
        max_loss_distance=round(account.distance_to_max_loss, 2),
        scaling_contracts=contracts,
        mode=config.execution.mode,
        current_regime=regime_str,
        regime_confidence=round(regime_conf, 3),
    )


@app.get("/api/agents", response_model=List[AgentStatus])
async def get_agents():
    """Get status of all strategy agents."""
    agents = get_all_agents()
    weights = _allocator.get_weights()

    statuses = []
    for agent in agents:
        statuses.append(AgentStatus(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            preferred_regimes=[r.value for r in agent.preferred_regimes] if agent.preferred_regimes else [],
            weight=round(weights.get(agent.agent_id, 1.0 / len(agents)), 4),
        ))

    return statuses


@app.get("/api/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Get detailed info for a specific agent."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    return {
        "agent_id": agent.agent_id,
        "agent_name": agent.agent_name,
        "version": agent.version,
        "preferred_regimes": [r.value for r in agent.preferred_regimes],
        "parameters": agent.get_parameters(),
        "min_confidence": agent.min_confidence_threshold,
    }


@app.post("/api/backtest", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """Run a backtest for a specific agent."""
    agent = get_agent(req.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {req.agent_id} not found")

    store = CandleStore()
    candles = store.get_candles(limit=req.days * 78)

    if candles.empty:
        raise HTTPException(status_code=400, detail="No candle data available")

    engine = BacktestEngine()

    if req.walk_forward:
        result = engine.walk_forward(agent, candles, req.train_days, req.test_days)
    else:
        result = engine.run(agent, candles)

    return BacktestResponse(
        agent_id=result.agent_id,
        oos_total_trades=result.oos_total_trades or result.is_total_trades,
        oos_win_rate=result.oos_win_rate or result.is_win_rate,
        oos_profit_factor=result.oos_profit_factor or result.is_profit_factor,
        oos_sharpe=result.oos_sharpe or result.is_sharpe,
        oos_max_drawdown=result.oos_max_drawdown or result.is_max_drawdown,
        oos_expectancy=result.oos_expectancy or result.is_expectancy,
        wf_num_windows=result.wf_num_windows,
        wf_pct_profitable_windows=result.wf_pct_profitable_windows,
        p_value=result.p_value,
        is_significant=result.is_significant,
        mc_probability_of_ruin=result.mc_probability_of_ruin,
        equity_curve=result.equity_curve[:500],  # Limit for JSON response
    )


@app.get("/api/trades", response_model=List[TradeRecord])
async def get_trades(limit: int = Query(50, le=500)):
    """Get trade history."""
    trades = _exec_engine.get_trade_history()[-limit:]
    return [
        TradeRecord(
            id=t.id,
            ts_open=t.ts_open.isoformat() if t.ts_open else "",
            ts_close=t.ts_close.isoformat() if t.ts_close else None,
            direction=t.direction.value,
            entry_price=t.entry_price,
            exit_price=t.exit_price or None,
            pnl=t.pnl or None,
            agent_signals=t.agent_signals_used,
            regime=t.regime.value if t.regime else "",
            mode=t.mode.value if t.mode else "sandbox",
        )
        for t in trades
    ]


@app.get("/api/candles")
async def get_candles(
    symbol: str = "MES",
    timeframe: str = "5min",
    limit: int = Query(500, le=5000),
):
    """Get candle data."""
    store = CandleStore()
    df = store.get_candles(symbol=symbol, timeframe=timeframe, limit=limit)
    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        records.append({
            "ts": row["ts"].isoformat() if hasattr(row["ts"], "isoformat") else str(row["ts"]),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        })
    return records


@app.get("/api/features")
async def get_features(limit: int = Query(100, le=500)):
    """Get current feature values."""
    store = CandleStore()
    candles = store.get_candles(limit=200)
    if candles.empty:
        return {}

    features = _engine.compute(candles)
    if features.empty:
        return {}

    # Return last N bars of features
    result = features.tail(limit).to_dict(orient="records")
    return result


@app.get("/api/regime")
async def get_regime():
    """Get current regime detection results."""
    store = CandleStore()
    candles = store.get_candles(limit=500)

    features = _engine.compute(candles)
    if features.empty:
        return {"regime": "unknown", "confidence": 0}

    try:
        _regime.fit(features)
        regime, conf = _regime.predict_current(features)

        # Get transition matrix
        trans_mat = _regime.get_transition_matrix()
        trans_dict = {}
        if trans_mat is not None:
            regimes = list(Regime)[:5]
            for i, r in enumerate(regimes):
                trans_dict[r.value] = {
                    regimes[j].value: round(float(trans_mat[i][j]), 4)
                    for j in range(min(len(regimes), trans_mat.shape[1]))
                }

        return {
            "regime": regime.value,
            "confidence": round(conf, 4),
            "transition_matrix": trans_dict,
        }
    except Exception as e:
        return {"regime": "unknown", "confidence": 0, "error": str(e)}


@app.get("/api/risk")
async def get_risk_status():
    """Get current risk management status."""
    account = _exec_engine.get_account_state()
    config = get_config()

    return {
        "balance": round(account.balance, 2),
        "peak_balance": round(account.peak_balance, 2),
        "drawdown": round(account.drawdown, 2),
        "drawdown_pct": round(account.drawdown_pct * 100, 2),
        "max_loss_floor": round(account.max_loss_floor, 2),
        "distance_to_max_loss": round(account.distance_to_max_loss, 2),
        "daily_pnl": round(account.daily_pnl, 2),
        "daily_trades": account.daily_trades,
        "consecutive_losses": account.consecutive_losses,
        "pdll": config.personal_risk.pdll,
        "pdpt": config.personal_risk.pdpt,
        "pdll_remaining": round(config.personal_risk.pdll + min(account.daily_pnl, 0), 2),
        "pdpt_remaining": round(config.personal_risk.pdpt - max(account.daily_pnl, 0), 2),
        "should_halt": account.should_halt,
        "compliance_log": _risk_mgr.get_compliance_log()[-10:],
    }


@app.get("/api/equity-curve")
async def get_equity_curve():
    """Get the equity curve."""
    return {"equity": _exec_engine.get_equity_curve()}


@app.get("/api/config")
async def get_system_config():
    """Get system configuration (non-sensitive)."""
    config = get_config()
    return {
        "prop_firm": {
            "name": config.prop_firm.name,
            "initial_balance": config.prop_firm.initial_balance,
            "max_loss_limit": config.prop_firm.max_loss_limit,
            "profit_target": config.prop_firm.profit_target,
        },
        "personal_risk": {
            "pdll": config.personal_risk.pdll,
            "pdpt": config.personal_risk.pdpt,
            "max_trades": config.personal_risk.max_trades_per_day,
            "max_risk_per_trade": config.personal_risk.max_risk_per_trade,
            "min_rr": config.personal_risk.min_risk_reward,
        },
        "execution": {
            "mode": config.execution.mode,
        },
        "allocator": {
            "method": config.allocator.combination_method,
            "min_confidence": config.allocator.min_combined_confidence,
        },
    }


# ── Data Management Endpoints ─────────────────────────────────────────────

@app.get("/api/data/status")
async def get_data_status():
    """Get status of all stored market data."""
    provider = YFinanceProvider()
    status = provider.get_data_status()

    # Add sample data info
    store = CandleStore()
    total = sum(info["count"] for info in status.values())

    return {
        "total_candles": total,
        "timeframes": status,
        "sources": ["sample_generator", "yfinance"],
    }


@app.post("/api/data/download")
async def download_data(req: DataDownloadRequest):
    """Download historical data from free sources."""
    if req.source != "yfinance":
        raise HTTPException(400, f"Unsupported source: {req.source}")

    provider = YFinanceProvider()

    if req.timeframe == "all":
        results = provider.download_multi_timeframe()
        total = sum(results.values())
        return {
            "status": "complete",
            "total_candles": total,
            "timeframes": results,
        }

    count = provider.download_and_store(
        timeframe=req.timeframe, days=req.days
    )
    return {
        "status": "complete",
        "candles_downloaded": count,
        "timeframe": req.timeframe,
    }


# ── Backtest All Agents ──────────────────────────────────────────────────

@app.post("/api/backtest/all", response_model=BacktestAllResponse)
async def run_backtest_all():
    """Run walk-forward backtest for ALL agents and compare results."""
    store = CandleStore()
    candles = store.get_candles(limit=10000)

    if candles.empty or len(candles) < 500:
        raise HTTPException(400, "Not enough candle data for backtesting")

    engine = BacktestEngine()
    agents = get_all_agents()
    results = []

    for agent in agents:
        try:
            result = engine.walk_forward(agent, candles, train_days=30, test_days=5)
            agent_result = {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "oos_trades": result.oos_total_trades,
                "oos_win_rate": result.oos_win_rate,
                "oos_profit_factor": result.oos_profit_factor,
                "oos_sharpe": result.oos_sharpe,
                "oos_max_drawdown": result.oos_max_drawdown,
                "oos_expectancy": result.oos_expectancy,
                "wf_windows": result.wf_num_windows,
                "wf_pct_profitable": result.wf_pct_profitable_windows,
                "mc_ruin_prob": result.mc_probability_of_ruin,
                "p_value": result.p_value,
                "is_significant": result.is_significant,
            }
            results.append(agent_result)
        except Exception as e:
            logger.error(f"Backtest failed for {agent.agent_id}: {e}")
            results.append({
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "error": str(e),
            })

    # Summary
    valid = [r for r in results if "oos_sharpe" in r]
    summary = {}
    if valid:
        best = max(valid, key=lambda x: x.get("oos_sharpe", -999))
        summary = {
            "total_agents": len(agents),
            "agents_with_trades": len([r for r in valid if r.get("oos_trades", 0) > 0]),
            "best_agent": best.get("agent_id"),
            "best_sharpe": best.get("oos_sharpe"),
            "avg_sharpe": round(
                sum(r.get("oos_sharpe", 0) for r in valid) / len(valid), 4
            ),
            "significant_agents": len([r for r in valid if r.get("is_significant")]),
        }

    return BacktestAllResponse(results=results, summary=summary)


# ── Evolution Endpoints ──────────────────────────────────────────────────

@app.post("/api/evolution/start")
async def start_evolution(req: EvolutionStartRequest):
    """Start genetic strategy evolution in background."""
    global _evolution_engine, _evolution_task, _evolution_status
    global _evolution_generations_target, _evolution_results

    if _evolution_status == "running":
        raise HTTPException(400, "Evolution already running")

    store = CandleStore()
    candles = store.get_candles(limit=10000)

    if candles.empty or len(candles) < 500:
        raise HTTPException(400, "Not enough candle data for evolution")

    _evolution_engine = EvolutionEngine()
    _evolution_engine.initialize_population(req.agent_types)
    _evolution_status = "running"
    _evolution_generations_target = req.generations
    _evolution_results = []

    async def _run_evolution():
        global _evolution_status, _evolution_results
        try:
            for gen in range(req.generations):
                if _evolution_status != "running":
                    break

                survivors = _evolution_engine.evolve_generation(candles)
                stats = _evolution_engine.get_generation_stats()

                gen_result = {
                    "generation": stats["generation"],
                    "best_fitness": round(stats["best_fitness"], 6),
                    "avg_fitness": round(float(stats["avg_fitness"]), 6),
                    "population_size": stats["population_size"],
                    "best_individual": {
                        "id": survivors[0].id if survivors else "",
                        "agent_type": survivors[0].agent_type if survivors else "",
                        "fitness": survivors[0].fitness if survivors else 0,
                        "oos_sharpe": survivors[0].oos_sharpe if survivors else 0,
                        "oos_pf": survivors[0].oos_profit_factor if survivors else 0,
                        "params": survivors[0].params if survivors else {},
                    } if survivors else {},
                }
                _evolution_results.append(gen_result)

                # Broadcast progress to WebSocket clients
                await broadcast_ws({
                    "type": "evolution_progress",
                    **gen_result,
                })

                # Yield control to event loop
                await asyncio.sleep(0.1)

            _evolution_status = "complete"
            await broadcast_ws({
                "type": "evolution_complete",
                "generations": len(_evolution_results),
                "best_fitness": _evolution_results[-1]["best_fitness"]
                if _evolution_results else 0,
            })

        except Exception as e:
            logger.error(f"Evolution error: {e}", exc_info=True)
            _evolution_status = "error"

    _evolution_task = asyncio.create_task(_run_evolution())

    return {
        "status": "started",
        "generations_target": req.generations,
        "population_size": len(_evolution_engine._population),
    }


@app.get("/api/evolution/status", response_model=EvolutionResponse)
async def get_evolution_status():
    """Get current evolution status and results."""
    if not _evolution_engine:
        return EvolutionResponse(status="idle")

    stats = _evolution_engine.get_generation_stats()
    best = _evolution_engine.get_best_individuals(5)

    best_list = [
        {
            "id": ind.id,
            "agent_type": ind.agent_type,
            "fitness": round(ind.fitness, 6),
            "oos_sharpe": round(ind.oos_sharpe, 4),
            "oos_profit_factor": round(ind.oos_profit_factor, 4),
            "oos_max_drawdown": round(ind.oos_max_drawdown, 2),
            "params": ind.params,
        }
        for ind in best
    ]

    return EvolutionResponse(
        generation=stats["generation"],
        population_size=stats["population_size"],
        best_fitness=round(stats["best_fitness"], 6),
        avg_fitness=round(float(stats["avg_fitness"]), 6),
        worst_fitness=round(stats["worst_fitness"], 6),
        status=_evolution_status,
        best_individuals=best_list,
    )


@app.post("/api/evolution/stop")
async def stop_evolution():
    """Stop the running evolution."""
    global _evolution_status, _evolution_task

    if _evolution_status != "running":
        raise HTTPException(400, "Evolution not running")

    _evolution_status = "stopped"

    if _evolution_task:
        _evolution_task.cancel()
        try:
            await _evolution_task
        except asyncio.CancelledError:
            pass

    return {
        "status": "stopped",
        "generations_completed": len(_evolution_results),
    }


@app.get("/api/evolution/history")
async def get_evolution_history():
    """Get full evolution history (all generation results)."""
    return {
        "status": _evolution_status,
        "generations": _evolution_results,
        "total_generations": len(_evolution_results),
    }


# ── Trading Control Endpoints ─────────────────────────────────────────────

@app.post("/api/trading/start")
async def start_trading(req: TradingStartRequest):
    """Start the trading orchestrator."""
    global _orchestrator, _orchestrator_task, _exec_engine, _risk_mgr, _allocator

    if _orchestrator and _orchestrator.status == OrchestratorStatus.RUNNING:
        raise HTTPException(400, "Trading loop already running")

    mode = TradingMode(req.mode)

    # Safety: LIVE mode requires explicit env var
    if mode == TradingMode.LIVE:
        if os.getenv("TRADOVATE_LIVE", "false").lower() != "true":
            raise HTTPException(
                403,
                "TRADOVATE_LIVE=true environment variable required for live trading"
            )

    _orchestrator = TradingOrchestrator(mode=mode, broadcast_fn=broadcast_ws)

    # Point module-level singletons to orchestrator's instances
    # so existing REST endpoints (/api/risk, /api/overview, etc.) reflect live state
    _exec_engine = _orchestrator.exec_engine
    _risk_mgr = _orchestrator.risk_manager
    _allocator = _orchestrator.allocator

    _orchestrator_task = asyncio.create_task(_orchestrator.start())

    logger.info(f"Trading orchestrator started in {mode.value} mode")
    return {"status": "started", "mode": mode.value}


@app.post("/api/trading/stop")
async def stop_trading():
    """Stop the trading orchestrator."""
    global _orchestrator, _orchestrator_task

    if not _orchestrator or _orchestrator.status == OrchestratorStatus.IDLE:
        raise HTTPException(400, "Trading loop not running")

    await _orchestrator.stop()

    if _orchestrator_task:
        _orchestrator_task.cancel()
        try:
            await _orchestrator_task
        except asyncio.CancelledError:
            pass

    logger.info("Trading orchestrator stopped")
    return {"status": "stopped"}


@app.get("/api/trading/status")
async def get_trading_status():
    """Get orchestrator status and metrics."""
    if not _orchestrator:
        return {"status": "idle", "mode": "sandbox", "metrics": {}}
    return _orchestrator.get_status()


@app.post("/api/trading/mode")
async def set_trading_mode(req: TradingModeRequest):
    """Switch trading mode. Stops and restarts the orchestrator."""
    new_mode = TradingMode(req.mode)

    # Safety: LIVE mode requires explicit env var
    if new_mode == TradingMode.LIVE:
        if os.getenv("TRADOVATE_LIVE", "false").lower() != "true":
            raise HTTPException(
                403,
                "TRADOVATE_LIVE=true environment variable required for live trading"
            )

    # Stop current orchestrator if running
    if _orchestrator and _orchestrator.status == OrchestratorStatus.RUNNING:
        await stop_trading()

    # Start with new mode
    return await start_trading(TradingStartRequest(mode=req.mode))


# ── WebSocket ────────────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """WebSocket for real-time updates."""
    await ws.accept()
    _ws_clients.append(ws)
    logger.info("WebSocket client connected")

    try:
        while True:
            data = await ws.receive_text()
            # Handle incoming commands from UI
            try:
                msg = json.loads(data)
                cmd = msg.get("command")

                if cmd == "get_status":
                    account = _exec_engine.get_account_state()
                    await ws.send_json({
                        "type": "status",
                        "balance": round(account.balance, 2),
                        "daily_pnl": round(account.daily_pnl, 2),
                        "position": bool(account.open_position),
                    })
                elif cmd == "flatten":
                    store = CandleStore()
                    latest = store.get_latest_candle()
                    if latest:
                        _exec_engine.flatten_all(latest.close, latest.ts, "Manual flatten")
                    await ws.send_json({"type": "flatten_confirmed"})
                elif cmd == "get_trading_status":
                    if _orchestrator:
                        await ws.send_json({
                            "type": "trading_status",
                            **_orchestrator.get_status(),
                        })
                    else:
                        await ws.send_json({
                            "type": "trading_status",
                            "status": "idle",
                        })

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        _ws_clients.remove(ws)
        logger.info("WebSocket client disconnected")


async def broadcast_ws(data: dict):
    """Broadcast to all connected WebSocket clients."""
    for ws in _ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            _ws_clients.remove(ws)


# ── Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    config = get_config()
    uvicorn.run(app, host="0.0.0.0", port=config.ui.api_port)
