# PropEdge: Adaptive Neural Trading System
## A Personal Institutional-Grade Quant Desk
### Complete Claude Code Build Instructions v2

> **VISION**: You are building a miniature version of how Renaissance Technologies, Citadel, or Two Sigma operate — but scaled down to one trader, one instrument (MES futures), and one prop firm (TopstepX $50K). The SYSTEM is the trader. Raymond is the risk manager and supervisor. The system continuously generates, tests, adapts, and executes strategies autonomously in sandbox — and eventually live once it proves itself profitable.

> **Builder Context**: Raymond is a Senior SRE (CKA certified, Kubernetes/AWS/GitOps expert) actively trading MES futures on TopstepX $50K combine. Current manual approach: 5-min charts, VWAP + 20 EMA, Break & Retest (SMC/BOS), $50 risk, $150 target (3:1 R:R), max 3 trades/day, $200 PDLL, $300 PDPT.

> **CRITICAL MINDSET**: This is NOT a trading journal with ML features. This is an autonomous adaptive trading system that happens to log everything it does. The neural network / ensemble IS the core — the journal, analytics, and UI are the observation layer for the human supervisor.

---

## ARCHITECTURAL PHILOSOPHY: HOW INSTITUTIONS ACTUALLY TRADE

Before writing any code, understand this mental model. This is how the big players operate, and we're replicating it at micro scale:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE INSTITUTIONAL MODEL                         │
│                                                                     │
│  LAYER 5: HUMAN OVERSIGHT (Raymond)                                │
│  ├── Monitor system health, approve/veto decisions                 │
│  ├── Set risk limits, define strategy universe                     │
│  └── Review performance, adjust parameters                        │
│                                                                     │
│  LAYER 4: RISK MANAGEMENT (The Governor)                           │
│  ├── Prop firm rule enforcement (hard limits, cannot be bypassed)  │
│  ├── Position sizing based on Kelly Criterion / fixed fractional   │
│  ├── Correlation checks (don't double up on same thesis)          │
│  ├── Drawdown circuit breakers                                     │
│  └── Regime-aware risk scaling (reduce size in uncertain regimes)  │
│                                                                     │
│  LAYER 3: META-STRATEGY / ALLOCATOR (The Brain)                   │
│  ├── Weights each strategy agent by recent out-of-sample perf     │
│  ├── Regime detection → which strategies fit current market?       │
│  ├── Signal combination (vote, weighted average, stacking)        │
│  ├── Confidence scoring → only trade high-conviction signals      │
│  └── Continuously A/B tests new strategies vs incumbents          │
│                                                                     │
│  LAYER 2: STRATEGY AGENTS (The Pods)                               │
│  ├── Agent 1: SMC Break & Retest                                  │
│  ├── Agent 2: VWAP Mean Reversion                                 │
│  ├── Agent 3: Opening Range Breakout                              │
│  ├── Agent 4: Order Block + FVG Confluence                        │
│  ├── Agent 5: Momentum / Trend Following                          │
│  ├── Agent 6: Neural Network (LSTM/Transformer)                   │
│  ├── Agent 7: Reinforcement Learning Agent                        │
│  ├── Agent N: [New strategies auto-discovered by the system]      │
│  │                                                                 │
│  │  Each agent independently:                                      │
│  │  - Generates BUY/SELL/HOLD signals with confidence scores      │
│  │  - Tracks its own P&L, win rate, Sharpe ratio                  │
│  │  - Self-adjusts parameters via walk-forward optimization       │
│  │  - Can be promoted, demoted, or killed by the Allocator        │
│  └──                                                               │
│                                                                     │
│  LAYER 1: MARKET DATA & FEATURE ENGINE (The Senses)               │
│  ├── Real-time price data (WebSocket from Tradovate/broker)       │
│  ├── Technical indicator calculation pipeline                      │
│  ├── Market microstructure features (volume, delta, order flow)   │
│  ├── Market structure detection (swing points, BOS, CHoCH)        │
│  ├── Regime classification (trending/ranging/volatile/quiet)      │
│  ├── News/sentiment ingestion                                      │
│  ├── Economic calendar awareness                                   │
│  └── Feature store (cached, versioned, reproducible)              │
│                                                                     │
│  LAYER 0: DATA INFRASTRUCTURE                                      │
│  ├── Historical data warehouse (DuckDB for analytics)             │
│  ├── Real-time event bus (local pub/sub for inter-layer comms)    │
│  ├── Trade execution engine (sandbox → paper → live)              │
│  └── Logging, audit trail, reproducibility                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

This architecture means:
- **Multiple strategies compete simultaneously** — the best ones get more weight
- **The system never stops learning** — background backtests run 24/7
- **Bad strategies get killed automatically** — Darwinian selection
- **New strategies can be born** — the system can propose and test new parameter combinations
- **Risk management is ABOVE everything** — no strategy can override the Governor
- **Raymond sees everything** — full transparency into what the system is thinking and why

---

## PHASE 0: DEEP RESEARCH (Do this FIRST — spend real time here)

### 0.1 — How Quantitative Hedge Funds Actually Work

This is the most important research. Don't skim this — internalize it.

```
Search and deeply read:
- "how Renaissance Technologies Medallion Fund works"
- "how Two Sigma trading system architecture"
- "how Citadel Securities market making works"
- "quantitative trading system architecture design"
- "multi-strategy hedge fund pod structure explained"
- "alpha signal combination portfolio construction"
- "Jim Simons Renaissance Technologies approach machine learning"

Key concepts to understand and document:
1. SIGNAL GENERATION vs SIGNAL COMBINATION
   - Institutions don't rely on one model. They generate hundreds of 
     weak signals and combine them into one strong signal.
   - Each signal alone might be 51% accurate — but 100 of them 
     combined can be 60-70% accurate.
   - Our system should work the same way: each strategy agent is a 
     weak signal. The meta-learner combines them.

2. REGIME DETECTION
   - Markets behave differently in different regimes
   - Trending markets reward momentum strategies
   - Ranging markets reward mean reversion
   - Volatile markets require tighter risk management
   - Institutions detect regimes and rotate strategies accordingly
   - Search: "Hidden Markov Model market regime detection Python"
   - Search: "market regime classification machine learning"

3. WALK-FORWARD VALIDATION (non-negotiable)
   - The #1 reason ML trading systems fail: overfitting
   - Institutions NEVER deploy a model tested only on training data
   - Walk-forward: train on window A, test on window B, slide forward
   - If in-sample Sharpe = 3.0 and out-of-sample Sharpe = 0.3, it's garbage
   - Search: "walk forward analysis trading Python implementation"
   - Search: "combinatorial purged cross validation financial ML"
   - Read: "Advances in Financial Machine Learning" by Marcos Lopez de Prado
     (Chapter on cross-validation for financial data)

4. THE KELLY CRITERION & POSITION SIZING
   - How institutions determine bet size based on edge magnitude
   - Full Kelly is too aggressive — use half-Kelly or quarter-Kelly
   - Search: "Kelly criterion futures trading position sizing"
   - This determines: given a signal with X% confidence, how many 
     MES contracts should we trade?

5. EXECUTION QUALITY
   - Slippage, fill assumptions, commission impact
   - Even on MES, 0.25-0.5 tick slippage per trade matters over 1000 trades
   - Our backtests MUST model realistic execution
   - Search: "realistic backtest assumptions futures slippage"
```

### 0.2 — Data Sources & Broker APIs

```
PRIORITY 1: Tradovate API (TopstepX uses this)
- Search: "Tradovate API documentation WebSocket"
- Search: "Tradovate REST API Python example"  
- Fetch: https://api.tradovate.com
- Research: demo/sandbox environment (FREE — this is our sandbox)
- Research: real-time WebSocket data format, order placement, position tracking
- Research: historical data availability through API
- Key: OAuth2 authentication flow, token refresh

PRIORITY 2: Historical Data for Backtesting
- Databento (https://databento.com) — tick/minute CME data, pay-per-use
  Search: "Databento MES futures historical data cost"
  This is the gold standard for futures data quality
  
- Polygon.io — has futures support on paid plans
  Search: "Polygon.io futures data API"
  
- First Rate Data / Kibot — bulk historical futures CSVs
  Search: "free historical MES futures data download"
  Search: "ES mini futures historical minute data free"
  
- Tiingo — some futures support
  Search: "Tiingo futures API"

PRIORITY 3: Alternative/Supplementary Data
- FRED API (free) — Fed funds rate, CPI, GDP, unemployment
  This feeds into our regime detection and event awareness
  
- Finnhub (free tier) — economic calendar, market news
  Search: "Finnhub economic calendar API"
  
- Quandl / Nasdaq Data Link — CFTC positioning data (COT reports)
  Search: "CFTC commitment of traders data API"
  Institutional positioning is a genuine edge signal
  
- VIX data — volatility regime proxy
  Search: "VIX historical data free download"

PRIORITY 4: Sentiment/Flow (nice to have, not MVP)
- Reddit API (r/FutureTrading, r/DayTrading)
- Twitter/X financial sentiment
- Options flow / gamma exposure levels
  Search: "gamma exposure GEX futures impact"
```

### 0.3 — Machine Learning for Trading: The Honest Truth

```
CRITICAL RESEARCH: Before building any ML, understand what actually works
and what is snake oil. Be brutally honest.

Search and deeply read:
- "does machine learning work for trading academic evidence"
- "why most algorithmic trading strategies fail"
- "overfitting in financial machine learning how to avoid"
- "Marcos Lopez de Prado triple barrier method"
- "machine learning trading strategies that actually work 2024 2025"
- "reinforcement learning trading real results not simulated"
- "LSTM stock prediction does it actually work out of sample"
- "random forest trading features that matter"
- "feature importance financial machine learning"
- "Ernie Chan quantitative trading strategies that work"

Key papers/resources to find and read:
1. "Advances in Financial Machine Learning" - Lopez de Prado
   - Triple barrier labeling method
   - Purged K-fold cross validation
   - Feature importance via MDA/MDI
   - Fractionally differentiated features
   
2. "Machine Learning for Algorithmic Trading" - Stefan Jansen
   - Practical implementations with Python
   - GitHub: https://github.com/stefan-jansen/machine-learning-for-trading

3. "Evidence-Based Technical Analysis" - David Aronson
   - Statistical rigor in evaluating trading rules
   - Multiple hypothesis testing correction
   - Why most "discovered" patterns are noise

4. FinRL framework
   - https://github.com/AI4Finance-Foundation/FinRL
   - Reinforcement learning for trading
   - Research their actual out-of-sample results (not just claims)

THE HONEST ANSWERS (based on academic consensus):
- Simple ML (random forest, XGBoost) CAN find weak edges in features
  that combine into meaningful signals — IF properly validated
- Deep learning (LSTM, Transformer) has mixed results — often overfits
  on financial data due to low signal-to-noise ratio
- Reinforcement learning is promising but extremely hard to train
  without massive overfitting
- The FEATURES matter more than the MODEL — garbage features with
  a perfect model = garbage output
- REGIME DETECTION is probably the highest-value ML application —
  knowing WHEN to trade matters more than knowing WHAT to trade
- ENSEMBLE METHODS (combining multiple weak learners) consistently
  outperform single models — this is why our multi-agent architecture
  is the right approach
```

### 0.4 — Smart Money Concepts: Quantified

```
Raymond's current strategy is SMC-based. We need to QUANTIFY it
so a computer can detect and execute it. Research deeply:

Market Structure Detection Algorithm:
- Search: "swing high swing low detection algorithm Python"
- Search: "fractal indicator market structure coding"
- Search: "break of structure BOS detection code"
- Search: "change of character CHoCH algorithm"
- Method: Use fractal pivots (N bars left, N bars right) to identify
  swing points. BOS = price breaks beyond prior swing. CHoCH = first
  BOS in opposite direction of trend.

Order Block Detection:
- Search: "order block detection algorithm Python trading"
- Search: "order block backtest results statistics"
- Definition: Last opposing candle before an impulsive move
- Quantification: Volume spike + large body candle before breakout

Fair Value Gap (FVG) Detection:
- Search: "fair value gap detection Python code"
- Search: "fair value gap fill rate statistics backtest"
- Definition: Gap between candle 1 high and candle 3 low (bullish)
  or candle 1 low and candle 3 high (bearish)
- Key stat to find: What % of FVGs get filled? In what timeframe?

Liquidity Concepts:
- Search: "liquidity sweep stop hunt algorithm detection"
- Search: "buy side sell side liquidity zones Python"
- Equal highs/lows = liquidity pools where stops accumulate
- Smart money sweeps these before reversing

VWAP as Institutional Reference:
- VWAP is literally what institutions use to benchmark execution
- Search: "VWAP trading strategy quantified backtest results"
- Search: "VWAP standard deviation bands mean reversion statistics"
- Deviation bands: +/- 1, 2, 3 standard deviations from VWAP

Kill Zones (Time-Based Edge):
- Search: "futures trading time of day edge statistics"
- Search: "ES futures intraday seasonality by hour"
- Hypothesis: Most volatility/opportunity in 8:30-11:00 ET (NY open)
- Must BACKTEST this — don't assume, prove it
```

### 0.5 — Prop Firm Compliance Rules (Hard-Coded Into Risk Layer)

```
TOPSTEPX $50K COMBINE (current account):
┌─────────────────────────────────────────────────────┐
│ HARD RULE (break = account dead):                   │
│ • Maximum Loss Limit: $2,000 trailing drawdown      │
│   - Trails from highest account balance (watermark) │
│   - Once it rises to $50,000, stays there forever   │
│   - Calculated at END of trading day                │
│                                                      │
│ OBJECTIVES (required to pass):                       │
│ • Profit Target: $3,000 (6% return)                 │
│ • Consistency: Best day < 50% of total profit       │
│ • No overnight positions (must be flat at close)    │
│                                                      │
│ DAILY LIMITS:                                        │
│ • Daily Loss Limit: REMOVED on TopstepX (Aug 2024) │
│   - But our system enforces Raymond's PDLL of $200  │
│ • Raymond's PDPT: $300 (personal daily profit cap)  │
│ • Max trades/day: 3 (Raymond's personal rule)       │
│                                                      │
│ SCALING PLAN (Express Funded Account):              │
│ • Start: 2 contracts (= 20 MES on TopstepX 10:1)   │
│ • Above $1,500 profit: 3 contracts (30 MES)        │
│ • Above $2,000 profit: 5 contracts (50 MES)        │
│                                                      │
│ ADDITIONAL:                                          │
│ • Commission-free on TopstepX                       │
│ • Level 1 data free, Level 2 = $39/month           │
│ • Permitted products: CME, CBOT, NYMEX, COMEX      │
│ • Trading hours: CME Globex hours (Sun-Fri)        │
│ • Only 0.96% of traders make Express → Live        │
└─────────────────────────────────────────────────────┘

These rules are NON-NEGOTIABLE in our system. The Risk Management layer
(Layer 4) enforces them as hard limits. No strategy agent, no matter
how confident, can override them. This is like a Kubernetes admission
controller — requests that violate policy get rejected before execution.
```

---

## PHASE 1: CORE SYSTEM ARCHITECTURE

### 1.1 — Project Structure

```bash
mkdir -p ~/propedge
cd ~/propedge

# Core system structure — think of each as a microservice
mkdir -p \
  core/                      # Shared types, config, event bus
  data_engine/               # Layer 0: Data infra, feature store
  feature_engine/            # Layer 1: Indicator/feature computation
  agents/                    # Layer 2: Individual strategy agents
  agents/smc_break_retest/
  agents/vwap_mean_reversion/
  agents/orb_breakout/
  agents/order_block_fvg/
  agents/momentum/
  agents/neural_net/
  agents/rl_agent/
  allocator/                 # Layer 3: Meta-strategy, signal combiner
  risk_manager/              # Layer 4: Prop firm compliance, sizing
  execution/                 # Order routing, sandbox, live
  backtester/                # Walk-forward backtesting engine
  trainer/                   # ML model training pipeline
  evolution/                 # Strategy evolution & genetic optimization
  ui/                        # React frontend (observation layer)
  api/                       # FastAPI backend
  data/historical/           # Cached market data
  data/models/               # Saved ML model weights
  data/features/             # Feature store cache
  data/trades/               # Trade log database
  configs/                   # All configuration
  scripts/                   # Utility scripts
  tests/                     # Test suite
```

### 1.2 — Technology Stack

```
BACKEND (Python — the entire brain runs here):
- Python 3.11+ (async support, performance improvements)
- FastAPI — API layer for UI communication
- asyncio — event loop for real-time processing
- DuckDB — analytical queries on trade/candle data (columnar, blazing fast)
- SQLite — operational data (trades, configs, state)
- Redis (optional) or in-memory pub/sub — event bus between layers
- pandas / polars — data manipulation (polars for speed on large datasets)
- numpy / scipy — numerical computation
- pandas-ta — technical indicator library (pure Python, no C deps)
- scikit-learn — classical ML models
- XGBoost / LightGBM — gradient boosting (our workhorse classifier)
- PyTorch — neural networks (LSTM, Transformer, RL)
- stable-baselines3 — reinforcement learning algorithms
- hmmlearn — Hidden Markov Models for regime detection
- optuna — hyperparameter optimization
- shap — model explainability
- websockets / aiohttp — broker API communication
- pydantic — data validation throughout

FRONTEND (React — the observation/control panel):
- React 18 + TypeScript
- Vite — build tool
- lightweight-charts — TradingView open-source charting library
- Recharts — analytics dashboards
- D3.js — custom visualizations
- TailwindCSS — styling (dark theme)
- Zustand — state management
- @tanstack/react-query — server state
- WebSocket client — real-time data from backend

LOCAL INFRA:
- Everything runs on localhost
- Single `docker-compose up` or `python main.py` to start
- No cloud dependencies for core functionality
- Data stored in local DuckDB/SQLite files
- Git for version control (strategies, configs, model weights)
```

### 1.3 — Event Bus Architecture

```
The system communicates via an internal event bus. Every layer publishes
and subscribes to events. This is how institutional systems work —
loosely coupled components that react to market state changes.

Event types:
┌─────────────────────────────────────────────────────────────────┐
│ MARKET EVENTS (from Data Engine)                                │
│ • price_update     {symbol, timestamp, ohlcv, bid, ask}       │
│ • candle_close     {symbol, timeframe, candle_data}            │
│ • volume_spike     {symbol, volume, avg_volume, ratio}         │
│ • news_event       {headline, impact, sentiment, source}       │
│ • economic_release {event, actual, forecast, previous}         │
│                                                                 │
│ FEATURE EVENTS (from Feature Engine)                           │
│ • features_updated {symbol, timeframe, feature_vector}         │
│ • regime_change    {old_regime, new_regime, confidence}         │
│ • structure_change {type: BOS|CHoCH, direction, level}         │
│ • fvg_formed       {type: bull|bear, top, bottom, timeframe}  │
│ • order_block      {type: bull|bear, zone_top, zone_bottom}   │
│                                                                 │
│ SIGNAL EVENTS (from Strategy Agents)                           │
│ • agent_signal     {agent_id, direction, confidence, sl, tp,  │
│                     reasoning, features_used}                   │
│                                                                 │
│ ALLOCATION EVENTS (from Meta-Strategy)                         │
│ • combined_signal  {direction, confidence, contributing_agents,│
│                     position_size, reasoning}                   │
│ • strategy_promoted  {agent_id, new_weight, reason}           │
│ • strategy_demoted   {agent_id, new_weight, reason}           │
│ • strategy_killed    {agent_id, reason, final_stats}          │
│                                                                 │
│ RISK EVENTS (from Risk Manager)                                │
│ • order_approved   {order_id, size_approved}                   │
│ • order_rejected   {order_id, reason}                          │
│ • risk_warning     {type, current_value, limit, pct_used}     │
│ • circuit_breaker  {reason, action: flatten|halt}              │
│ • compliance_update {rule, status, margin_remaining}           │
│                                                                 │
│ EXECUTION EVENTS (from Execution Engine)                       │
│ • order_submitted  {order_id, type, price, qty}               │
│ • order_filled     {order_id, fill_price, slippage}           │
│ • position_opened  {trade_id, entry, sl, tp, agent_id}       │
│ • position_closed  {trade_id, exit, pnl, duration}           │
│                                                                 │
│ SYSTEM EVENTS                                                   │
│ • backtest_complete {strategy_id, results}                     │
│ • model_retrained   {model_id, metrics, improvement}          │
│ • daily_report      {date, summary_stats}                     │
│ • session_start     {date, pre_market_analysis}               │
│ • session_end       {date, review}                             │
└─────────────────────────────────────────────────────────────────┘

Implementation: Use Python asyncio queues or a simple in-process
pub/sub. No need for Kafka/RabbitMQ — this all runs locally.
Every event is logged to DuckDB for replay and analysis.
```

---

## PHASE 2: LAYER 0 — DATA INFRASTRUCTURE

### 2.1 — Database Schema

```sql
-- Use DuckDB for all analytical queries (columnar, fast aggregations)
-- Use SQLite for operational state (current positions, active orders)

-- ============ DUCKDB (Analytics) ============

-- Raw candle data (the foundation of everything)
CREATE TABLE candles (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,        -- '1min', '5min', '15min', '1hour', '1day'
    ts TIMESTAMP NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    volume DOUBLE,
    tick_count INTEGER,                -- Number of ticks in candle
    vwap DOUBLE,                       -- Volume-weighted average price
    buy_volume DOUBLE,                 -- Volume on upticks (if available)
    sell_volume DOUBLE,                -- Volume on downticks
    delta DOUBLE,                      -- buy_volume - sell_volume
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Pre-computed feature vectors (the Feature Store)
CREATE TABLE features (
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    feature_json VARCHAR,              -- Full feature vector as JSON
    -- Also store key features as columns for fast SQL queries:
    regime VARCHAR,                    -- 'trending_up','trending_down','ranging','volatile'
    regime_confidence DOUBLE,
    market_structure VARCHAR,          -- 'bullish', 'bearish', 'transitioning'
    vwap_distance_atr DOUBLE,         -- Distance from VWAP in ATR units
    ema20_distance_atr DOUBLE,
    rsi_14 DOUBLE,
    atr_14 DOUBLE,
    volume_ratio DOUBLE,              -- current vol / 20-period avg vol
    is_kill_zone BOOLEAN,
    kill_zone_name VARCHAR,
    minutes_to_news INTEGER,          -- Minutes until next high-impact event
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Every signal generated by every agent (for analysis/replay)
CREATE TABLE agent_signals (
    id VARCHAR PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    agent_id VARCHAR NOT NULL,
    agent_version VARCHAR,
    symbol VARCHAR NOT NULL,
    direction VARCHAR,                 -- 'LONG', 'SHORT', 'FLAT'
    confidence DOUBLE,                 -- 0.0 to 1.0
    entry_price DOUBLE,
    stop_loss DOUBLE,
    take_profit DOUBLE,
    risk_reward_ratio DOUBLE,
    features_snapshot VARCHAR,         -- JSON: what the agent saw
    reasoning VARCHAR,                 -- Human-readable explanation
    was_taken BOOLEAN DEFAULT FALSE,   -- Did the allocator use this signal?
    outcome_if_taken DOUBLE,           -- Hypothetical P&L (calculated after)
    actual_pnl DOUBLE,                -- Actual P&L if it was taken
    regime_at_signal VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trade log (every executed trade, sandbox or live)
CREATE TABLE trades (
    id VARCHAR PRIMARY KEY,
    ts_open TIMESTAMP NOT NULL,
    ts_close TIMESTAMP,
    symbol VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    entry_price DOUBLE NOT NULL,
    exit_price DOUBLE,
    quantity INTEGER NOT NULL,
    stop_loss DOUBLE,
    take_profit DOUBLE,
    pnl DOUBLE,
    pnl_ticks DOUBLE,
    commission DOUBLE DEFAULT 0,
    slippage_ticks DOUBLE,
    
    -- What generated this trade
    agent_signals_used VARCHAR,        -- JSON array of agent_signal IDs
    combined_confidence DOUBLE,        -- Allocator's final confidence
    position_size_reason VARCHAR,      -- Why this size was chosen
    
    -- Market context snapshot
    regime VARCHAR,
    market_structure VARCHAR,
    session VARCHAR,
    vwap_position VARCHAR,
    atr_at_entry DOUBLE,
    features_at_entry VARCHAR,         -- Full feature vector JSON
    
    -- Psychology (if Raymond is manually supervising)
    manual_override BOOLEAN DEFAULT FALSE,
    override_reason VARCHAR,
    emotion_tag VARCHAR,
    followed_system BOOLEAN,
    
    -- Prop firm tracking
    account_balance_before DOUBLE,
    account_balance_after DOUBLE,
    max_loss_limit_distance DOUBLE,    -- How far from blowing up
    daily_pnl_before DOUBLE,
    daily_pnl_after DOUBLE,
    
    -- Execution quality
    intended_entry DOUBLE,             -- What we wanted
    actual_entry DOUBLE,               -- What we got
    entry_slippage DOUBLE,
    intended_exit DOUBLE,
    actual_exit DOUBLE,
    exit_slippage DOUBLE,
    
    mode VARCHAR DEFAULT 'sandbox',    -- 'sandbox', 'paper', 'live'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent performance tracking (updated daily)
CREATE TABLE agent_performance (
    agent_id VARCHAR NOT NULL,
    date DATE NOT NULL,
    
    -- Signal quality metrics
    signals_generated INTEGER,
    signals_taken INTEGER,
    signals_profitable INTEGER,
    signal_accuracy DOUBLE,
    avg_confidence DOUBLE,
    
    -- Trading metrics
    total_pnl DOUBLE,
    win_rate DOUBLE,
    profit_factor DOUBLE,
    avg_win DOUBLE,
    avg_loss DOUBLE,
    max_drawdown DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    expectancy DOUBLE,                 -- avg $ per trade
    
    -- Meta-strategy weight
    current_weight DOUBLE,             -- 0.0 to 1.0 allocation weight
    weight_trend VARCHAR,              -- 'increasing', 'stable', 'decreasing'
    
    -- Walk-forward out-of-sample metrics
    oos_sharpe DOUBLE,
    oos_profit_factor DOUBLE,
    oos_win_rate DOUBLE,
    oos_degradation DOUBLE,            -- How much worse than in-sample?
    
    PRIMARY KEY (agent_id, date)
);

-- Regime log (for analyzing which regimes produce which results)
CREATE TABLE regime_log (
    ts TIMESTAMP PRIMARY KEY,
    regime VARCHAR NOT NULL,
    confidence DOUBLE,
    duration_minutes INTEGER,          -- How long has this regime lasted?
    features_json VARCHAR,             -- What features define this regime?
    hmm_state INTEGER,                 -- Hidden Markov Model state index
    volatility_percentile DOUBLE,      -- Current vol vs historical
    trend_strength DOUBLE              -- ADX or similar
);

-- Backtesting results archive
CREATE TABLE backtest_results (
    id VARCHAR PRIMARY KEY,
    agent_id VARCHAR NOT NULL,
    run_timestamp TIMESTAMP NOT NULL,
    
    -- Data range
    train_start DATE,
    train_end DATE,
    test_start DATE,
    test_end DATE,
    
    -- In-sample metrics
    is_total_trades INTEGER,
    is_win_rate DOUBLE,
    is_profit_factor DOUBLE,
    is_sharpe DOUBLE,
    is_max_drawdown DOUBLE,
    is_expectancy DOUBLE,
    
    -- Out-of-sample metrics (THIS IS WHAT MATTERS)
    oos_total_trades INTEGER,
    oos_win_rate DOUBLE,
    oos_profit_factor DOUBLE,
    oos_sharpe DOUBLE,
    oos_max_drawdown DOUBLE,
    oos_expectancy DOUBLE,
    
    -- Walk-forward summary
    wf_num_windows INTEGER,
    wf_avg_oos_sharpe DOUBLE,
    wf_std_oos_sharpe DOUBLE,
    wf_pct_profitable_windows DOUBLE,  -- What % of OOS windows were profitable?
    wf_worst_window_sharpe DOUBLE,
    
    -- Monte Carlo
    mc_median_return DOUBLE,
    mc_5th_percentile_return DOUBLE,   -- Worst 5% of random sequences
    mc_95th_percentile_return DOUBLE,
    mc_probability_of_ruin DOUBLE,     -- P(hitting max loss) over N trades
    
    -- Statistical significance
    p_value DOUBLE,                    -- Is this edge statistically significant?
    is_significant BOOLEAN,            -- p < 0.05?
    
    -- Comparison to baselines
    vs_random_sharpe DOUBLE,           -- How much better than random entries?
    vs_buy_hold_sharpe DOUBLE,
    
    params_json VARCHAR,               -- Strategy parameters used
    model_path VARCHAR,                -- Path to saved model (if ML)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evolution tracker (for genetic strategy optimization)
CREATE TABLE strategy_evolution (
    generation INTEGER NOT NULL,
    individual_id VARCHAR NOT NULL,
    parent_ids VARCHAR,                -- JSON array of parent strategy IDs
    params_json VARCHAR NOT NULL,
    fitness_score DOUBLE,              -- Combined metric used for selection
    oos_sharpe DOUBLE,
    oos_profit_factor DOUBLE,
    oos_max_drawdown DOUBLE,
    survived BOOLEAN DEFAULT FALSE,    -- Made it to next generation?
    promoted_to_agent BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (generation, individual_id)
);

-- Prop firm compliance ledger (append-only audit trail)
CREATE TABLE compliance_log (
    ts TIMESTAMP NOT NULL,
    event_type VARCHAR NOT NULL,       -- 'check', 'warning', 'violation', 'block'
    rule VARCHAR NOT NULL,             -- 'max_loss_limit', 'daily_loss', 'scaling', etc
    current_value DOUBLE,
    limit_value DOUBLE,
    pct_used DOUBLE,
    action_taken VARCHAR,              -- 'none', 'warned', 'blocked_trade', 'flattened'
    details VARCHAR
);

-- Daily session records
CREATE TABLE sessions (
    date DATE PRIMARY KEY,
    
    -- Pre-session
    pre_market_bias VARCHAR,
    regime_at_open VARCHAR,
    key_levels_json VARCHAR,
    economic_events_json VARCHAR,
    agents_active_json VARCHAR,        -- Which agents are trading today
    agent_weights_json VARCHAR,        -- Current allocation weights
    
    -- During session
    total_signals_generated INTEGER,
    total_signals_taken INTEGER,
    total_trades INTEGER,
    
    -- Post-session
    total_pnl DOUBLE,
    best_agent VARCHAR,
    worst_agent VARCHAR,
    regime_changes INTEGER,
    compliance_warnings INTEGER,
    
    -- Review (Raymond fills this in)
    system_grade VARCHAR,              -- A-F: how well did the system perform?
    override_count INTEGER,            -- How many times did Raymond override?
    override_was_right INTEGER,        -- How many overrides were correct?
    notes VARCHAR,
    lessons VARCHAR
);
```

---

## PHASE 3: LAYER 1 — FEATURE ENGINE

### 3.1 — Feature Computation Pipeline

```python
"""
The Feature Engine transforms raw candle data into the feature vectors
that every strategy agent and ML model consumes. This is the MOST
IMPORTANT engineering component — better features = better everything.

The engine runs on every new candle close and publishes updated features
to the event bus. All agents receive the same features but interpret
them differently.

Architecture:
  raw candles → indicator pipeline → structure detection → 
  regime classification → feature vector → feature store + event bus
"""

class FeatureEngine:
    """
    Computes ~80-100 features organized into categories.
    Each feature is normalized (z-score or percentile rank) so ML models
    can consume them without additional preprocessing.
    """
    
    def compute_all(self, candles: DataFrame) -> FeatureVector:
        """
        FEATURE CATEGORIES:
        
        1. PRICE ACTION (15 features)
        - returns: 1-bar, 5-bar, 15-bar, 60-bar log returns
        - range: high-low range / ATR (is this bar unusually large?)
        - body: |close - open| / (high - low) (how decisive is this candle?)
        - position_in_range: (close - low) / (high - low) (closing near high or low?)
        - gap: open vs prior close (gap up/down)
        - higher_high: bool, higher_low: bool (trend continuation)
        - new_swing_high: bool, new_swing_low: bool
        - bars_since_swing_high, bars_since_swing_low
        - distance_to_swing_high_atr, distance_to_swing_low_atr
        
        2. TREND INDICATORS (12 features)
        - ema_8: distance from price in ATR units + slope (rate of change)
        - ema_20: distance from price in ATR units + slope
        - ema_50: distance from price in ATR units + slope
        - ema_alignment: 1.0 if 8>20>50 (bullish), -1.0 if reversed, 0 if mixed
        - macd: line, signal, histogram (all normalized)
        - adx_14: trend strength (0-100)
        - linear_regression_slope_20: fitted slope of last 20 bars
        
        3. MEAN REVERSION (10 features)
        - rsi_14, rsi_7 (standard RSI)
        - rsi_divergence: bool (price makes new high but RSI doesn't)
        - bollinger_position: (price - lower) / (upper - lower)
        - bollinger_bandwidth: (upper - lower) / middle (volatility proxy)
        - vwap_distance_atr: distance from VWAP in ATR units
        - vwap_std_position: which std dev band (e.g., +1.5 or -2.3)
        - stochastic_k, stochastic_d
        - cci_20: Commodity Channel Index
        
        4. VOLUME / ORDER FLOW (10 features)
        - volume_ratio: current / SMA(20) volume
        - volume_trend: is volume increasing or decreasing?
        - delta: buy_volume - sell_volume (if available)
        - cumulative_delta_trend: direction of cumulative delta
        - on_balance_volume_trend: OBV slope
        - volume_at_price_poc: is current price near high-volume node?
        - relative_volume_spike: bool (volume > 2x average)
        
        5. VOLATILITY (8 features)
        - atr_14: raw ATR in points
        - atr_percentile: current ATR vs last 100 days (0-100)
        - atr_expansion: atr_14 / atr_50 (expanding or contracting?)
        - keltner_width: Keltner channel width
        - bollinger_bandwidth (also in mean reversion)
        - parkinson_volatility: intraday range-based vol estimate
        - realized_vol_5day vs implied_vol (if VIX data available)
        - is_low_vol_squeeze: bool (BB inside Keltner = squeeze)
        
        6. MARKET STRUCTURE / SMC (15 features)
        - market_structure: 'bullish', 'bearish', 'transitioning'
        - last_bos_direction: 'up' or 'down'
        - bars_since_bos: how recent was the break of structure?
        - last_choch_bars_ago: bars since change of character
        - is_in_fvg: bool (price is inside a fair value gap)
        - fvg_type: 'bullish', 'bearish', None
        - nearest_ob_distance_atr: distance to nearest order block
        - nearest_ob_type: 'bullish', 'bearish', None
        - liquidity_above_distance: distance to nearest equal highs
        - liquidity_below_distance: distance to nearest equal lows
        - displacement_magnitude: size of last impulsive move in ATR
        - order_flow_imbalance: bid/ask imbalance if DOM data available
        - premium_discount: is price in premium (>50% of range) or discount?
        - inducement_detected: bool (minor liquidity sweep before OB)
        
        7. TIME / CALENDAR (10 features)
        - hour_sin, hour_cos: cyclical encoding of hour
        - minute_sin, minute_cos: cyclical encoding of minute
        - day_of_week_sin, day_of_week_cos: cyclical encoding
        - is_kill_zone: bool (London 2-5am, NY 8-11am, PM 1-3pm ET)
        - kill_zone_id: 0=none, 1=london, 2=ny_am, 3=ny_pm
        - minutes_to_next_event: minutes until next high-impact release
        - is_event_day: bool (FOMC, NFP, CPI, etc.)
        - is_first_30min: bool (opening range period)
        - is_last_30min: bool (approaching close)
        - is_lunch_hour: bool (11:30am-1:00pm ET, typically low volume)
        
        8. REGIME (computed by HMM, fed back as features)
        - regime_id: integer state from Hidden Markov Model
        - regime_name: human-readable label
        - regime_confidence: probability of being in this regime
        - regime_duration: how many bars in current regime
        - regime_transition_prob: probability of regime change soon
        """
        pass
```

### 3.2 — Regime Detection Engine

```
This is arguably the single highest-value ML component. Build this FIRST.

The regime detector uses a Hidden Markov Model (HMM) to classify the
current market into one of several states. Strategy agents use this
to know WHEN to be active.

States to detect:
1. TRENDING_UP: Strong bullish trend, momentum strategies work
2. TRENDING_DOWN: Strong bearish trend, momentum strategies work
3. RANGING: Sideways chop, mean reversion strategies work
4. VOLATILE_EXPANSION: High volatility breakout, careful sizing
5. QUIET_COMPRESSION: Low vol squeeze, preparing for expansion

Features to feed into HMM:
- ATR percentile (volatility level)
- ATR rate of change (expanding or contracting)
- ADX value (trend strength)
- Bollinger bandwidth
- Returns autocorrelation (trending = positive, mean reverting = negative)
- Volume trend

Training:
- Fit HMM on 1-2 years of historical data
- Validate regime labels make intuitive sense (plot on chart)
- Walk-forward validate: retrain monthly, does it generalize?

Search: "Hidden Markov Model market regime detection Python hmmlearn"
Search: "market regime detection features financial"
Search: "regime switching model trading strategy"

CRITICAL: The regime detector is a FILTER, not a signal generator.
It tells other agents whether NOW is a good time for THEIR strategy.
- Regime = TRENDING → activate momentum agents, deactivate mean reversion
- Regime = RANGING → activate mean reversion, deactivate momentum
- Regime = VOLATILE → reduce position sizes across all agents
- Regime = QUIET → prepare for breakout, reduce trade frequency
```

---

## PHASE 4: LAYER 2 — STRATEGY AGENTS

### 4.1 — Agent Base Class

```python
"""
Every strategy agent implements this interface. Agents are independent —
they don't know about each other. The Allocator (Layer 3) combines their
signals. Think of each agent as a portfolio manager at a multi-strat fund.
"""

class StrategyAgent(ABC):
    agent_id: str
    agent_name: str
    version: str
    preferred_regimes: List[str]       # Which regimes this agent excels in
    min_confidence_threshold: float     # Don't emit signal below this
    
    @abstractmethod
    def on_features(self, features: FeatureVector) -> Optional[Signal]:
        """
        Called on every new candle close with updated features.
        Returns a Signal if the agent sees an opportunity, or None.
        
        A Signal contains:
        - direction: LONG | SHORT
        - confidence: 0.0 to 1.0
        - entry_price: suggested entry
        - stop_loss: hard stop
        - take_profit: target
        - risk_reward: calculated R:R
        - reasoning: human-readable explanation of WHY
        - features_used: which features drove this decision
        - regime_context: current regime and how it affects this signal
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict:
        """Return current strategy parameters (for optimization)"""
        pass
    
    @abstractmethod
    def set_parameters(self, params: Dict):
        """Update strategy parameters (for walk-forward optimization)"""
        pass
    
    def should_be_active(self, current_regime: str) -> bool:
        """Is this agent suited for the current market regime?"""
        return current_regime in self.preferred_regimes
    
    def get_performance_stats(self) -> AgentStats:
        """Query agent_performance table for this agent"""
        pass
```

### 4.2 — Agent Catalog (Build These)

```
BUILD IN THIS ORDER (easiest to hardest, most proven to most experimental):

AGENT 1: SMC Break & Retest ("smc_br")
  Preferred regimes: TRENDING_UP, TRENDING_DOWN
  Logic:
    1. Detect market structure via swing points
    2. Identify Break of Structure (BOS)
    3. Wait for price to retest the broken level
    4. Entry on rejection candle at retest zone
    5. Stop below retest zone (bullish) or above (bearish)
    6. Target: 3:1 R:R
  Confirmation filters:
    - VWAP alignment (price above VWAP for longs, below for shorts)
    - EMA 20 slope confirms direction
    - Volume spike on the BOS candle
    - Must be in kill zone (NY open preferred)
  Backtest focus: Does BOS + retest actually produce an edge?

AGENT 2: VWAP Mean Reversion ("vwap_mr")
  Preferred regimes: RANGING
  Logic:
    1. Calculate VWAP with 1, 2, 3 standard deviation bands
    2. Entry when price touches +/- 2 std dev band
    3. Confirmation: RSI divergence OR volume climax
    4. Target: return to VWAP
    5. Stop: beyond +/- 3 std dev
  Backtest focus: What's the fill rate for VWAP +2 std → VWAP?

AGENT 3: Opening Range Breakout ("orb")
  Preferred regimes: TRENDING_UP, TRENDING_DOWN, VOLATILE_EXPANSION
  Logic:
    1. Define opening range = first 15 or 30 min of NY session
    2. Breakout above/below range with volume > 1.5x average
    3. Entry on breakout or retest of range boundary
    4. Stop: opposite side of range OR middle of range
    5. Target: 1.5x or 2x range width
  Backtest focus: ORB on MES — what range definition works best?

AGENT 4: Order Block + FVG Confluence ("ob_fvg")
  Preferred regimes: TRENDING_UP, TRENDING_DOWN
  Logic:
    1. Identify order blocks (last opposing candle before impulse)
    2. Identify Fair Value Gaps (3-candle pattern with gap)
    3. Entry ONLY where OB and FVG overlap (confluence zone)
    4. Higher timeframe must confirm direction
    5. Stop below OB zone, target at opposing liquidity
  Backtest focus: Does OB+FVG confluence improve win rate over either alone?

AGENT 5: Momentum Trend Follower ("momentum")
  Preferred regimes: TRENDING_UP, TRENDING_DOWN
  Logic:
    1. EMA 8 > EMA 20 > EMA 50 for longs (reverse for shorts)
    2. ADX > 25 confirms trend strength
    3. Entry on pullback to EMA 20 with bullish/bearish engulfing
    4. Stop below EMA 50 or recent swing low
    5. Trail stop using EMA 20 once in profit
  Backtest focus: Simple moving average systems on MES intraday

AGENT 6: XGBoost Classifier ("xgb_classifier")
  Preferred regimes: ALL (self-adapts via features)
  Logic:
    1. Input: full feature vector (~80 features)
    2. Target: triple barrier label (UP/DOWN/FLAT based on 
       whether price hits +X ticks or -X ticks first within N bars)
    3. Output: probability of UP, probability of DOWN
    4. Only emit signal when P(direction) > 0.6
    5. Use SHAP values to explain each prediction
  Training:
    - Walk-forward: 60-day train, 5-day test, slide 5 days
    - Retrain weekly with latest data
    - Track feature importance drift over time
    - Compare against random baseline

AGENT 7: LSTM Sequence Model ("lstm_seq")
  Preferred regimes: ALL (learns regime sensitivity from data)
  Logic:
    1. Input: sequence of last 60 feature vectors
    2. Architecture: 2-layer LSTM → Dense → Softmax (UP/DOWN/FLAT)
    3. Also outputs predicted magnitude (how far will it move?)
    4. Only emit signal when confidence > 0.65
  Training:
    - Walk-forward with purged cross-validation
    - Dropout 0.3, recurrent dropout 0.2
    - Learning rate scheduling
    - Early stopping on validation loss
    - VERY prone to overfitting — monitor obsessively

AGENT 8: Reinforcement Learning Agent ("rl_ppo")
  Preferred regimes: ALL (learns when to trade and when not to)
  Logic:
    1. Environment: Custom Gymnasium env simulating MES trading
    2. State: last 30 feature vectors + current position + account state
    3. Actions: BUY, SELL, HOLD, CLOSE_POSITION
    4. Reward function:
       - Sharpe-adjusted returns (not raw P&L — prevents overtrading)
       - Penalty for max drawdown > X%
       - Penalty for trading outside kill zones
       - Bonus for consistency (low variance in daily returns)
       - Penalty for prop firm rule violations
    5. Algorithm: PPO via stable-baselines3
  Training:
    - Train on 1-2 years of data
    - Validate on 6 months unseen data
    - Multiple random seeds to check robustness
    - Compare against buy-and-hold AND against simple rule-based agents
    - If RL agent can't beat Agent 1 out-of-sample, it stays demoted

FUTURE AGENTS (auto-generated by evolution system):
AGENT N: Genetically-evolved parameter variants of Agents 1-5
AGENT N+1: Transformer-based sequence model
AGENT N+2: Ensemble of N other agents (meta-meta agent)
```

---

## PHASE 5: LAYER 3 — THE ALLOCATOR (Meta-Strategy)

### 5.1 — Signal Combination

```
The Allocator is the BRAIN. It receives signals from all active agents
and produces a single combined decision. This is how institutions work —
they don't let each pod trade independently; a central risk/allocation
function combines everything.

COMBINATION METHODS (implement all, compare which works best):

Method 1: WEIGHTED VOTE
  - Each agent has a weight based on recent OOS performance
  - Combined signal = Σ(agent_weight × agent_confidence × agent_direction)
  - If combined signal > threshold → trade it
  - Weights updated daily based on rolling 20-day OOS Sharpe

Method 2: STACKING (Meta-Learner)
  - Train a simple model (logistic regression or small XGBoost)
  - Input: each agent's signal + confidence + regime
  - Output: probability of profitable trade
  - Trained on the HISTORICAL SIGNALS of agents (not raw features)
  - This learns WHEN to trust each agent and when to ignore them

Method 3: REGIME-CONDITIONAL SELECTION
  - In TRENDING regime: only listen to momentum + SMC + ORB agents
  - In RANGING regime: only listen to VWAP MR + OB/FVG agents
  - In VOLATILE regime: only listen to ML agents (they're adaptive)
  - In QUIET regime: reduce all signals, wait for expansion
  - Within each regime, use weighted vote among active agents

Method 4: UNANIMOUS CONSENT (most conservative)
  - Only trade when 3+ agents agree on direction
  - Highest confidence filter: combined confidence must be > 0.7
  - Lowest trade frequency but potentially highest win rate
  - Good for prop firm compliance (fewer trades = fewer mistakes)

The Allocator also handles:
- CONFLICT RESOLUTION: If Agent 1 says LONG and Agent 2 says SHORT,
  default to FLAT unless one has significantly higher confidence
- SIGNAL DECAY: Signals expire after N bars (default 3) if not acted on
- COOLDOWN: After a loss, wait N bars before next signal (anti-tilt)
- CONCENTRATION RISK: Don't take correlated signals from similar agents
```

### 5.2 — Darwinian Strategy Evolution

```
This is what makes the system ADAPTIVE — it continuously breeds new
strategies, tests them, and promotes winners.

EVOLUTION LOOP (runs in background, continuously):

1. MUTATION: Take a profitable agent's parameters, randomly adjust 1-3
   parameters within ±20% range. Backtest the mutation.
   
2. CROSSOVER: Take parameters from two profitable agents, combine them
   (e.g., Agent 1's entry logic + Agent 3's exit logic). Backtest.

3. EVALUATION: Run walk-forward backtest on every new variant.
   Fitness function = (OOS Sharpe × OOS Profit Factor) / max_drawdown
   
4. SELECTION: Top 10% survive. Bottom 90% are killed.
   Survivors get promoted to paper trading alongside real agents.

5. PROMOTION: If a paper-traded variant outperforms its parent over
   20+ trades, it gets promoted to live trading and the parent gets
   its weight reduced.

6. EXTINCTION: If an agent's rolling 30-day OOS Sharpe drops below 0
   for 3 consecutive retraining cycles, it gets killed.

This creates a continuously evolving strategy pool. The system gets
BETTER over time without manual intervention.

Implementation:
- Use Optuna for parameter optimization
- Run evolution batches during off-market hours (overnight)
- Log every generation to strategy_evolution table
- Visualize the "family tree" of strategies in the UI
- Set a MAX number of active agents (e.g., 8) to prevent chaos
```

---

## PHASE 6: LAYER 4 — RISK MANAGEMENT (The Governor)

```
This is the layer that keeps you ALIVE. It sits above everything and
has absolute veto power. No other layer can override it.

IMPLEMENTATION AS A PIPELINE:

Combined Signal from Allocator
    ↓
[1] REGIME RISK FILTER
    - Is current regime suitable for trading? (confidence > 0.6)
    - If QUIET or uncertain regime: reject unless confidence > 0.8
    ↓
[2] PROP FIRM COMPLIANCE CHECK
    - Will this trade violate the trailing max loss limit?
      Calculate worst case: if stopped out, does balance > floor?
    - Are we within scaling plan contract limits?
    - Is there an open position? (no stacking unless allowed)
    - Are we approaching session close? (must flatten before close)
    ↓
[3] PERSONAL RISK LIMITS
    - Have we hit PDLL ($200 daily loss)? → HALT for day
    - Have we hit PDPT ($300 daily profit)? → HALT for day
    - Have we hit max trades (3/day)? → HALT for day
    - Is there a high-impact news event in next 5 minutes? → WAIT
    ↓
[4] POSITION SIZING (Kelly/Fixed Fractional)
    - Given the signal confidence and current account state:
    - Kelly fraction = (win_rate × avg_win - (1-win_rate) × avg_loss) / avg_win
    - Use quarter-Kelly for safety
    - Never risk more than $50 per trade (Raymond's rule)
    - Adjust size for regime volatility
    ↓
[5] EXECUTION QUALITY CHECK
    - Is the spread acceptable? (not during illiquid hours)
    - Is the stop loss at a logical level? (not in the middle of noise)
    - Is the risk:reward ratio >= 2:1? (reject < 2:1)
    ↓
[6] APPROVED → Send to Execution Engine
    OR
    REJECTED → Log reason, notify UI, continue monitoring

CIRCUIT BREAKERS (automatic, cannot be overridden):
- 2 consecutive losses → pause 15 minutes (anti-tilt)
- 3 losses in a day → HALT trading for the day
- Account within $200 of max loss limit → HALT until tomorrow
- System error or data gap detected → flatten all positions immediately
- Latency to broker > 5 seconds → halt new orders
```

---

## PHASE 7: EXECUTION ENGINE & SANDBOX

```
The execution engine handles the actual order routing. It operates
in THREE modes, all using the same code path:

MODE 1: SANDBOX (Historical Replay)
  - Feeds historical candle data as if it were live
  - Simulates fills with configurable slippage (default: 1 tick random)
  - Replay speed: 1x, 5x, 20x, 100x, MAX
  - Perfect for rapid strategy testing and system development
  - Can replay specific dates (e.g., "show me how the system would
    have handled the March 2024 FOMC day")

MODE 2: PAPER (Live Data, Simulated Execution)
  - Connects to Tradovate demo WebSocket for real-time MES data
  - Simulates fills using real live quotes + slippage model
  - Tracks virtual account balance with full prop firm rules
  - This is where the system PROVES ITSELF before going live
  - Minimum 30 days of profitable paper trading before enabling live

MODE 3: LIVE (Real Money, Real Execution)
  - Same code path as Paper but sends real orders to Tradovate
  - Additional safety: human confirmation required for first 2 weeks
  - Maximum position size reduced by 50% vs paper for first month
  - Kill switch: one keystroke flattens everything
  - Automated shutdown if daily loss exceeds $150 (below PDLL of $200)
  
FILL SIMULATION MODEL (for Sandbox and Paper):
  - Market orders: fill at current ask (buy) or bid (sell) + random
    slippage uniform(0, 0.5) ticks
  - Limit orders: fill when price crosses limit level, with 30%
    probability of NOT filling even when touched (realistic for MES)
  - Stop orders: fill at stop level + random slippage uniform(0, 1.0) ticks
  - Commission: $0.00 on TopstepX (commission-free)
  - Partial fills: not modeled (MES is liquid enough for our size)
```

---

## PHASE 8: BACKGROUND LEARNING SYSTEM

```
This runs 24/7 — even when markets are closed. The system is ALWAYS
learning, testing, evolving. Think of it as the quant research team
that never sleeps.

CONTINUOUS TASKS:

[1] WALK-FORWARD RETRAINING (runs nightly)
    For each ML agent (XGBoost, LSTM, RL):
    - Add today's data to the training set
    - Retrain on rolling window (last 60 days)
    - Validate on last 5 days (out-of-sample)
    - Compare new model vs old model on holdout
    - If new model is better → swap it in
    - If worse → keep old model, log degradation
    - Alert Raymond if model is degrading consistently

[2] STRATEGY EVOLUTION (runs overnight)
    - Generate 50-100 parameter mutations of top-performing agents
    - Walk-forward backtest each mutation
    - Select top performers for paper trading
    - Kill underperformers
    - Log everything to strategy_evolution table

[3] FEATURE IMPORTANCE ANALYSIS (runs weekly)
    - Which features are actually predictive?
    - Has predictive power shifted? (feature drift)
    - Are there new feature combinations worth trying?
    - SHAP analysis on XGBoost to understand decision drivers
    - Generate report for Raymond to review

[4] REGIME ANALYSIS (runs daily)
    - How did each regime perform this week?
    - Are regime transitions becoming more frequent?
    - Which agents performed best in each regime?
    - Update regime-conditional allocation weights

[5] EXECUTION QUALITY ANALYSIS (runs daily)
    - Compare intended vs actual fills
    - Track slippage trends
    - Identify times of day with best/worst execution
    - Update slippage model for backtester

[6] STATISTICAL SIGNIFICANCE TESTING (runs weekly)
    - For each agent: is its edge still statistically significant?
    - Run permutation tests: shuffle entry times, recompute returns
    - If p-value > 0.10 → agent's edge may be decaying → flag it
    - If p-value > 0.20 → strongly consider deactivating

[7] CORRELATION MONITORING (runs daily)
    - Are agents generating correlated signals?
    - If Agent 1 and Agent 4 have 0.9 correlation → we're not
      diversified, we're doubling down on the same thesis
    - Alert if agent correlation exceeds 0.7
```

---

## PHASE 9: FRONTEND (The Observation Deck)

```
The UI is Raymond's window into the system's brain. It should feel
like a Bloomberg terminal meets a NASA mission control.

CRITICAL VIEWS:

1. COMMAND CENTER (Home Dashboard)
   ┌────────────────────────────────────────────────────────┐
   │  SYSTEM STATUS: ACTIVE | Mode: SANDBOX | MES: 5847.50 │
   │                                                        │
   │  [Regime: TRENDING_UP (78%)]  [Session: NY Open]       │
   │                                                        │
   │  Today's P&L: +$127.50        Trades: 2/3             │
   │  PDLL Used: $0 / $200         PDPT: $127.50 / $300    │
   │  Max Loss Distance: $1,872    Scaling: 2 contracts     │
   │                                                        │
   │  ┌─ AGENT STATUS ──────────────────────────────────┐   │
   │  │ smc_br:     ACTIVE  ████████░░ 0.34 weight      │   │
   │  │ vwap_mr:    PAUSED  (wrong regime)               │   │
   │  │ orb:        ACTIVE  █████░░░░░ 0.22 weight      │   │
   │  │ xgb:        ACTIVE  ██████░░░░ 0.28 weight      │   │
   │  │ lstm:       ACTIVE  ████░░░░░░ 0.16 weight      │   │
   │  │ rl_ppo:     PAPER   (testing, 12 days left)      │   │
   │  └─────────────────────────────────────────────────┘   │
   │                                                        │
   │  LAST SIGNAL: LONG @ 5845.00 | Confidence: 0.73       │
   │  Contributing: smc_br(0.85), xgb(0.71), orb(0.62)     │
   │  Risk: $37.50 (0.75 contracts MES)                     │
   │  Status: FILLED @ 5845.25 | Current P&L: +$6.25       │
   └────────────────────────────────────────────────────────┘

2. LIVE CHART VIEW
   - TradingView lightweight-charts with real-time data
   - Overlay: VWAP + bands, EMA 20, detected order blocks, FVGs
   - Agent signals plotted as arrows (color-coded by agent)
   - Regime shown as background color bands
   - Current positions shown as entry/SL/TP lines
   - Upcoming economic events as vertical markers

3. AGENT DEEP DIVE
   - Select any agent → see its full history
   - Equity curve (in-sample AND out-of-sample clearly separated)
   - Win rate, Sharpe, profit factor over time (rolling windows)
   - Signal heatmap: when does this agent fire? (hour × day matrix)
   - Feature importance (SHAP values for ML agents)
   - Last 20 signals with outcome and reasoning
   - Walk-forward degradation chart
   - Comparison vs random baseline

4. ALLOCATOR VIEW ("The Brain")
   - Current weights for all agents (pie chart)
   - Weight changes over time (line chart)
   - Regime history with agent activation overlay
   - Signal correlation matrix between agents
   - Combined signal confidence distribution
   - Agent promotion/demotion history

5. RISK DASHBOARD
   - Prop firm compliance gauges (visual meters)
   - Trailing max loss limit visualization over time
   - Daily P&L with PDLL/PDPT bands
   - Position size history vs Kelly-optimal
   - Circuit breaker trigger history
   - Monte Carlo probability of ruin

6. EVOLUTION LAB
   - Strategy family tree visualization
   - Generation performance over time
   - Currently paper-trading variants
   - Parameter sensitivity heatmaps
   - Best vs worst mutations

7. BACKTEST CENTER
   - Run backtests on any agent or combination
   - Visual equity curve with trade markers
   - Drawdown chart
   - Walk-forward window results
   - Statistical significance p-values
   - Monte Carlo distribution of outcomes
   - Side-by-side comparison of strategies

8. RESEARCH / LEARNING LOG
   - What the system learned today (auto-generated)
   - Feature drift alerts
   - Model degradation warnings
   - Suggested improvements
   - Raymond's manual notes and overrides
```

---

## PHASE 10: DEVELOPMENT SPRINTS

```
Sprint 1 (Days 1-4): Foundation + Data
  - Project scaffolding with full directory structure
  - DuckDB schema creation and migration scripts
  - Event bus implementation (asyncio pub/sub)
  - Historical data loader (fetch MES data from best free source)
  - Basic candle storage and retrieval
  - Config system (YAML-based)

Sprint 2 (Days 5-9): Feature Engine + Regime Detection
  - Full feature computation pipeline (~80 features)
  - Market structure detection (swing points, BOS, CHoCH)
  - FVG and order block detection
  - Hidden Markov Model regime detector
  - Feature store (write to DuckDB, cache in memory)
  - Unit tests for all feature computations

Sprint 3 (Days 10-14): First Strategy Agents
  - Agent base class and registration system
  - Agent 1: SMC Break & Retest
  - Agent 2: VWAP Mean Reversion
  - Agent 3: Opening Range Breakout
  - Backtesting engine with realistic fills
  - Walk-forward validation framework
  - Backtest results stored in DuckDB

Sprint 4 (Days 15-19): ML Agents
  - Agent 6: XGBoost classifier with triple barrier labeling
  - Walk-forward training pipeline
  - Feature importance (SHAP)
  - Agent 7: LSTM sequence model
  - Statistical significance testing
  - Model serialization and versioning

Sprint 5 (Days 20-24): Allocator + Risk Manager
  - Signal combination (weighted vote, regime-conditional)
  - Agent weight management (performance-based)
  - Full risk management pipeline
  - Prop firm compliance engine
  - Position sizing (Kelly criterion)
  - Circuit breakers
  - Compliance audit logging

Sprint 6 (Days 25-29): Execution + Sandbox
  - Tradovate API connector (demo account)
  - WebSocket real-time data streaming
  - Sandbox execution engine (replay mode)
  - Paper trading execution (live data, sim fills)
  - Full event flow: data → features → agents → allocator → risk → execute

Sprint 7 (Days 30-35): Frontend
  - React app scaffolding with dark theme
  - Command Center dashboard
  - Live chart with TradingView lightweight-charts
  - Agent status and performance views
  - Risk dashboard with compliance gauges
  - WebSocket connection to backend for real-time updates

Sprint 8 (Days 36-42): Evolution + Learning System
  - Background learning loop (nightly retraining)
  - Strategy evolution system (mutation, crossover, selection)
  - RL agent (PPO) training environment
  - Feature drift monitoring
  - Automated reporting
  - System health monitoring

Sprint 9 (Days 43-49): Integration + Paper Trading
  - End-to-end system test on historical data
  - 2-week paper trading shakedown
  - Performance benchmarking vs random
  - Bug fixes and edge case handling
  - Documentation

Sprint 10 (Day 50+): Live Preparation
  - Minimum 30 days of profitable paper trading
  - Live execution path with human-in-the-loop
  - Kill switch implementation
  - Disaster recovery procedures
  - Go/no-go checklist
```

---

## ABSOLUTE RULES — NEVER VIOLATE THESE

```
1. RISK MANAGEMENT CANNOT BE BYPASSED
   No signal, no matter how confident, overrides the Risk Manager.
   If the Governor says no, the answer is no. Period.

2. OUT-OF-SAMPLE ONLY
   Never make a trading decision based on in-sample results.
   If you can't prove it works on unseen data, it doesn't work.

3. COMPARE AGAINST RANDOM
   Every agent must be compared against random entry timing.
   If your strategy can't beat random by a statistically significant
   margin (p < 0.05), it has no edge. Kill it.

4. SANDBOX → PAPER → LIVE
   Never skip stages. 30 days minimum at each level before advancing.
   The system must PROVE itself at each stage.

5. THE SYSTEM IS THE TRADER
   Raymond supervises. The system decides. If Raymond has to override
   more than 20% of the time, the system isn't ready.

6. LOG EVERYTHING
   Every signal, every decision, every override, every feature vector.
   If you can't reproduce a result, it doesn't count.

7. ASSUME OVERFITTING UNTIL PROVEN OTHERWISE
   Every result is guilty until proven innocent by walk-forward
   validation, statistical significance tests, and out-of-sample
   evaluation. Most "edges" are noise. Prove they're not.

8. KEEP API COSTS MINIMAL
   - Tradovate demo = free
   - Historical data = find free/cheap sources first
   - ML runs locally = free
   - Only pay for data when we've proven the system works in sandbox
```
