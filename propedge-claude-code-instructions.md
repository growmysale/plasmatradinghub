# PropEdge: AI-Powered Trading Journal & Edge Discovery Platform
## Complete Claude Code Build Instructions

> **Context**: You are building PropEdge — an AI-powered trading journal and edge-finding platform built specifically for funded/prop firm futures traders (TopStep, Apex, FTMO, etc.). The builder (Raymond) is an SRE by trade, actively trading MES futures on a TopstepX $50K combine, using 5-min charts with VWAP + 20 EMA, Break & Retest (SMC/BOS) strategy, $50 risk per trade, $150 profit target (3:1 R:R), max 3 trades/day.

---

## PHASE 0: DEEP RESEARCH (Do this FIRST before writing any code)

### 0.1 — Trading Platform APIs & Data Sources

Research each of these thoroughly using web browser. For each, document: authentication method, websocket vs REST, rate limits, sandbox/paper trading support, and cost.

**Priority broker APIs to research (futures-focused):**
```
- Tradovate API (used by TopstepX) — https://api.tradovate.com
  - REST + WebSocket, OAuth2, free sandbox environment
  - Research: contract specs, order types, account endpoints
  - This is the #1 priority — TopstepX traders use Tradovate

- Rithmic API (used by many prop firms)
  - Research: R | Protocol API, connection requirements
  - Note: Rithmic requires vendor agreement, more complex

- NinjaTrader API
  - Research: Connection.dll, ATI interface
  - Note: Desktop-only, less suitable for web app

- Interactive Brokers TWS API
  - Research: Client Portal API (REST) vs TWS API
  - Free paper trading account available

- CQG API
  - Research: WebAPI, used by some prop firms
```

**Free / low-cost market data sources to research:**
```
- Databento (https://databento.com) — tick-level CME futures data, pay-per-use
  Research: MES/ES historical data costs, real-time feed costs, Python SDK

- Polygon.io — has futures data on paid plans
  Research: futures coverage, websocket streaming, historical data access

- Alpha Vantage — free tier available
  Research: futures support (limited), rate limits

- Yahoo Finance (yfinance) — free but delayed/limited for futures
  Research: ES=F symbol support, limitations

- CBOE/CME DataMine — official historical data
  Research: cost for MES/ES historical tick data

- TradingView (unofficial) — lightweight-charts library for rendering
  Research: Can embed charts, but data is separate concern

- Quandl/Nasdaq Data Link — some free futures datasets
  Research: CME futures historical data availability
```

**News & Sentiment APIs:**
```
- Benzinga Pro API — real-time news, economic calendar
- NewsAPI.org — general news aggregation, free tier
- Alpha Vantage News Sentiment — free tier
- Finnhub — economic calendar, news, free tier
- FRED API (Federal Reserve) — economic data, free
- CME FedWatch — rate probabilities (scrape or API)
- Twitter/X API — trader sentiment (expensive now)
- Reddit API — r/FutureTrading, r/DayTrading sentiment
- Unusual Whales — options flow data
```

### 0.2 — Trading Strategy Research (Think Like a New Human Trader)

Approach this as if you're Raymond — dropped into the trading world and need to find an actual edge. Research each strategy domain deeply:

**Smart Money Concepts (SMC) / ICT Methodology:**
```
Research and document:
- Market structure: swing highs/lows, BOS (Break of Structure), CHoCH (Change of Character)
- Order blocks: bullish/bearish, how to identify programmatically
- Fair Value Gaps (FVG) / imbalances: definition, fill rates, tradeable setups
- Liquidity concepts: buy-side/sell-side liquidity sweeps, stop hunts
- Optimal Trade Entry (OTE): Fibonacci retracement 62-79% zone
- Kill zones: London (2-5am ET), NY (8-11am ET), PM session
- ICT power of 3: accumulation, manipulation, distribution
- Judas swing: fake move before true direction

Key research URLs:
- Search: "ICT Smart Money Concepts backtesting results"
- Search: "order block detection algorithm python"
- Search: "fair value gap trading strategy backtest win rate"
- Search: "SMC trading strategy quantified results academic"
```

**Volume Profile / Market Microstructure:**
```
Research and document:
- VWAP: standard, anchored, deviation bands
- Volume Profile: POC (Point of Control), Value Area High/Low
- Delta volume: cumulative delta, delta divergences
- Order flow: bid/ask imbalance, absorption, exhaustion
- Footprint charts: how to build from tick data
- Market depth (DOM): how to read and use for futures

Search: "volume profile trading strategy backtest"
Search: "order flow analysis futures python"
Search: "VWAP deviation bands mean reversion strategy"
```

**Mean Reversion Strategies:**
```
Research and document:
- Bollinger Band squeeze → expansion
- RSI divergence (regular + hidden)
- VWAP mean reversion: entry at +/- 2 std dev, target VWAP
- Opening range breakout (ORB) failure = mean reversion
- Statistical mean reversion: z-score based

Search: "mean reversion futures intraday strategy backtest"
Search: "MES mean reversion VWAP strategy results"
```

**Trend Following / Momentum:**
```
Research and document:
- EMA crossover systems (8/21, 9/20, 20/50)
- MACD histogram momentum
- ADX trend strength filter
- Donchian channel breakouts
- Supertrend indicator

Search: "trend following futures intraday backtest results"
Search: "EMA crossover MES futures strategy performance"
```

**Machine Learning Approaches:**
```
Research and document:
- Feature engineering for price data: returns, volatility, volume ratios
- LSTM/GRU for time series prediction: does it actually work?
- Random Forest / XGBoost for classification (up/down/flat)
- Reinforcement Learning for trading: PPO, A2C agents
- Regime detection: Hidden Markov Models for market states
- Clustering: K-means for identifying similar market conditions
- Transformer models for financial time series

CRITICAL — research the HONEST results:
Search: "machine learning trading does it work academic paper"
Search: "reinforcement learning trading real results not overfitting"
Search: "LSTM stock prediction out of sample performance"
Search: "why most ML trading strategies fail overfitting"
Search: "walk forward optimization trading strategy"
```

**Prop Firm Rules (MUST understand to build proper risk management):**
```
Research specific rules for:
- TopstepX: daily loss limit, max drawdown, profit target, scaling plan
- Apex Trader Funding: trailing drawdown, consistency rule
- FTMO: daily loss 5%, max loss 10%, minimum trading days
- MyFundedFutures: drawdown rules
- Earn2Trade: rules and evaluation criteria

Search: "TopstepX combine rules 2025 2026"
Search: "prop firm funded trader pass rate statistics"
Search: "prop firm rules comparison 2025"
```

### 0.3 — Trading Psychology & Books Research

```
Research the most impactful trading books and extract key principles:
- "Trading in the Zone" by Mark Douglas — belief systems, probabilistic thinking
- "The Disciplined Trader" by Mark Douglas — emotional patterns
- "Reminiscences of a Stock Operator" — tape reading, market psychology
- "Market Wizards" series by Jack Schwager — common traits of winners
- "The Art and Science of Technical Analysis" by Adam Grimes
- "Evidence-Based Technical Analysis" by David Aronson — statistical rigor
- "Advances in Financial Machine Learning" by Marcos Lopez de Prado
- "Fooled by Randomness" by Nassim Taleb — survivorship bias in trading

Search: "best trading books proven strategies"
Search: "trading psychology research academic papers"
Search: "behavioral finance biases day traders"

Key psychological principles to encode into the platform:
1. Loss aversion → track revenge trades, tilt detection
2. Overtrading → enforce max trades/day rule
3. Recency bias → show long-term stats alongside recent
4. Confirmation bias → present contrarian data alongside setups
5. Disposition effect → track tendency to cut winners early
```

### 0.4 — Technical Architecture Research

```
Research the best stack for a locally-run, easily-updatable trading platform:

Desktop App Framework:
- Tauri (Rust + Web frontend) — lightweight, fast, small binary
  Search: "Tauri desktop app trading platform"
- Electron — heavier but more ecosystem support
  Search: "Electron trading app performance"
- RECOMMENDATION: Tauri for production, but start with pure web app
  served locally for speed of development

Backend:
- Python (FastAPI) for ML/backtesting/data processing
  - backtrader, vectorbt, or custom backtesting engine
  - scikit-learn, pytorch, tensorflow for ML
  - pandas, numpy for data manipulation
- Node.js/Bun for real-time websocket handling
- SQLite for local data storage (portable, no server needed)
- DuckDB for analytical queries on trade data (columnar, fast)

Frontend:
- React + TypeScript
- lightweight-charts (TradingView charting library — FREE, open source)
  Search: "tradingview lightweight-charts documentation"
  https://github.com/nicholasgasior/lightweight-charts
- Recharts or D3 for analytics dashboards
- TailwindCSS for styling

Real-time Data:
- WebSocket connections to broker API
- Local caching with SQLite/DuckDB
- Event-driven architecture for live updates

Research update/distribution mechanism:
- GitHub Releases + auto-update for Tauri
- Simple `git pull && npm run build` for dev phase
- Docker container option for easy deployment
```

---

## PHASE 1: PROJECT SCAFFOLDING

### 1.1 — Initialize Project Structure

```bash
# Create project root
mkdir -p ~/propedge
cd ~/propedge

# Initialize monorepo structure
mkdir -p \
  packages/frontend          # React UI
  packages/backend           # Python FastAPI backend
  packages/engine            # Trading engine (Python)
  packages/ml                # ML models and training
  packages/connectors        # Broker API connectors
  data/historical            # Historical price data
  data/models                # Trained ML models
  data/journals              # Trade journal entries
  configs                    # Strategy configs, API keys
  docs                       # Documentation
  scripts                    # Utility scripts

# Initialize frontend
cd packages/frontend
npm init -y
npm install react react-dom typescript @types/react @types/react-dom
npm install lightweight-charts recharts lucide-react tailwindcss
npm install @tanstack/react-query zustand           # State management
npm install vite @vitejs/plugin-react               # Build tool
npm install -D postcss autoprefixer

# Initialize backend
cd ../backend
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn websockets aiohttp
pip install sqlalchemy alembic                       # Database
pip install pandas numpy scipy                       # Data processing
pip install duckdb                                   # Analytics queries

# Initialize engine
cd ../engine
pip install backtrader                               # Backtesting (or vectorbt)
pip install vectorbt                                 # Alternative backtester
pip install ta-lib                                   # Technical indicators (if available)
pip install pandas-ta                                # Pure Python TA (no C dependency)
pip install scikit-learn xgboost lightgbm            # ML
pip install torch                                    # PyTorch for neural nets
pip install gymnasium                                # RL environment

# Initialize connectors
cd ../connectors
pip install tradovate-api                            # If available, else build custom
pip install websocket-client aiohttp
```

### 1.2 — Configuration Files

Create `configs/default.yaml`:
```yaml
# PropEdge Configuration
app:
  name: "PropEdge"
  version: "0.1.0"
  mode: "sandbox"  # sandbox | paper | live
  port: 8080

# Prop Firm Profile
prop_firm:
  name: "TopstepX"
  account_size: 50000
  daily_loss_limit: 1000    # Research actual TopstepX limits
  max_drawdown: 2000        # Research actual TopstepX limits
  profit_target: 3000       # Research actual TopstepX limits
  max_contracts: 5          # Research actual TopstepX limits

# Risk Management
risk:
  max_risk_per_trade: 50     # Dollars
  profit_target_per_trade: 150  # Dollars (3:1 R:R)
  max_trades_per_day: 3
  max_daily_loss: 200        # Personal daily loss limit (PDLL)
  max_daily_profit: 300      # Personal daily profit target (PDPT)
  max_position_size: 2       # Max MES contracts at once
  
# Default Strategy Parameters
strategy:
  primary: "smc_break_retest"
  timeframe: "5min"
  instruments:
    - symbol: "MESM5"       # MES June 2025 (update quarterly)
      exchange: "CME"
      tick_size: 0.25
      tick_value: 1.25       # $1.25 per tick on MES
      point_value: 5.0       # $5.00 per point on MES
  indicators:
    - type: "VWAP"
    - type: "EMA"
      period: 20
  kill_zones:
    london_open: "02:00-05:00"     # ET
    ny_open: "08:00-11:00"          # ET
    ny_afternoon: "13:00-15:00"     # ET

# Data Sources (fill in API keys)
data:
  historical_provider: "databento"  # or polygon, alpaca
  news_provider: "finnhub"
  economic_calendar: "fred"
  
# ML Configuration
ml:
  walk_forward:
    train_window_days: 60
    test_window_days: 5
    retrain_frequency: "weekly"
  features:
    - returns_1bar
    - returns_5bar
    - volume_ratio
    - vwap_distance
    - ema20_distance
    - atr_14
    - rsi_14
    - hour_of_day
    - day_of_week
    - delta_volume
```

---

## PHASE 2: DATABASE SCHEMA & CORE DATA MODEL

### 2.1 — SQLite Schema

Create `packages/backend/schema.sql`:
```sql
-- Core trade journal
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    timestamp_open DATETIME NOT NULL,
    timestamp_close DATETIME,
    symbol TEXT NOT NULL,
    direction TEXT CHECK(direction IN ('LONG', 'SHORT')) NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity INTEGER NOT NULL DEFAULT 1,
    stop_loss REAL,
    take_profit REAL,
    pnl REAL,
    pnl_ticks REAL,
    commission REAL DEFAULT 0,
    
    -- Strategy metadata
    strategy TEXT,
    setup_type TEXT,          -- e.g., "BOS_retest", "FVG_fill", "VWAP_bounce"
    timeframe TEXT,
    
    -- Market context at entry
    market_structure TEXT,    -- "bullish", "bearish", "ranging"
    session TEXT,             -- "london", "ny_open", "ny_pm", "asia"
    vwap_position TEXT,       -- "above", "below", "at"
    ema20_position TEXT,      -- "above", "below", "at"
    atr_at_entry REAL,
    volume_at_entry REAL,
    
    -- Psychology & discipline
    emotion_pre TEXT,         -- "calm", "fomo", "revenge", "confident", "anxious"
    emotion_post TEXT,
    followed_plan BOOLEAN,
    plan_deviation_notes TEXT,
    confidence_level INTEGER CHECK(confidence_level BETWEEN 1 AND 5),
    
    -- Screenshots & notes
    chart_screenshot_path TEXT,
    notes TEXT,
    lessons_learned TEXT,
    
    -- Tags for filtering
    tags TEXT,                -- JSON array: ["A+_setup", "news_catalyst", "FOMC_day"]
    
    -- Prop firm tracking
    prop_firm_account TEXT,
    daily_pnl_before REAL,   -- Account P&L before this trade
    daily_pnl_after REAL,    -- Account P&L after this trade
    drawdown_remaining REAL,  -- How much drawdown room left
    
    -- Sandbox vs Live
    is_sandbox BOOLEAN DEFAULT TRUE,
    source TEXT DEFAULT 'manual', -- "manual", "auto_import", "sandbox_engine"
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Daily performance tracking
CREATE TABLE daily_stats (
    date TEXT PRIMARY KEY,
    total_pnl REAL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    largest_win REAL,
    largest_loss REAL,
    average_win REAL,
    average_loss REAL,
    profit_factor REAL,
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,
    max_drawdown_intraday REAL,
    followed_plan_pct REAL,
    emotion_score REAL,        -- Aggregated emotional discipline score
    notes TEXT,
    
    -- Prop firm daily tracking
    account_balance REAL,
    daily_loss_limit_used REAL,
    max_drawdown_used REAL
);

-- Strategy definitions & backtesting results
CREATE TABLE strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    rules_json TEXT,           -- Machine-readable rules
    entry_conditions TEXT,     -- Human-readable
    exit_conditions TEXT,
    risk_management TEXT,
    
    -- Backtesting results
    backtest_start_date TEXT,
    backtest_end_date TEXT,
    backtest_total_trades INTEGER,
    backtest_win_rate REAL,
    backtest_profit_factor REAL,
    backtest_max_drawdown REAL,
    backtest_sharpe_ratio REAL,
    backtest_expectancy REAL,  -- Average $ per trade
    
    -- Live results
    live_total_trades INTEGER DEFAULT 0,
    live_win_rate REAL,
    live_profit_factor REAL,
    live_expectancy REAL,
    
    -- Walk-forward results
    wf_out_of_sample_pf REAL,
    wf_robustness_score REAL,
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Market data cache (for local backtesting)
CREATE TABLE candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    vwap REAL,
    delta_volume REAL,        -- Buy volume - sell volume
    PRIMARY KEY (symbol, timeframe, timestamp)
);

-- ML model performance tracking
CREATE TABLE ml_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,                 -- "classifier", "regressor", "rl_agent"
    features_json TEXT,
    hyperparams_json TEXT,
    train_start TEXT,
    train_end TEXT,
    test_start TEXT,
    test_end TEXT,
    
    -- Performance metrics
    accuracy REAL,
    precision_score REAL,
    recall REAL,
    f1_score REAL,
    sharpe_ratio REAL,
    profit_factor REAL,
    max_drawdown REAL,
    total_return REAL,
    
    -- Walk-forward validation
    wf_avg_accuracy REAL,
    wf_std_accuracy REAL,
    wf_degradation_rate REAL,  -- How fast does it decay out of sample?
    
    model_path TEXT,           -- Path to saved model file
    is_active BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Economic calendar events
CREATE TABLE economic_events (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    event_name TEXT NOT NULL,
    country TEXT,
    impact TEXT CHECK(impact IN ('low', 'medium', 'high')),
    actual TEXT,
    forecast TEXT,
    previous TEXT,
    market_reaction_es REAL,   -- ES point move in 5min after
    market_reaction_description TEXT
);

-- Trade plan / pre-market analysis
CREATE TABLE daily_plans (
    date TEXT PRIMARY KEY,
    pre_market_bias TEXT,       -- "bullish", "bearish", "neutral"
    key_levels_json TEXT,       -- {"resistance": [4500, 4520], "support": [4480, 4460]}
    economic_events_today TEXT, -- JSON array of events
    overnight_context TEXT,     -- Asia/London session notes
    plan_notes TEXT,
    max_trades_planned INTEGER DEFAULT 3,
    strategies_for_today TEXT,  -- JSON array of strategy IDs
    
    -- Post-session review
    review_notes TEXT,
    grade TEXT CHECK(grade IN ('A', 'B', 'C', 'D', 'F')),
    biggest_mistake TEXT,
    best_decision TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX idx_trades_date ON trades(timestamp_open);
CREATE INDEX idx_trades_strategy ON trades(strategy);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_sandbox ON trades(is_sandbox);
CREATE INDEX idx_candles_lookup ON candles(symbol, timeframe, timestamp);
```

---

## PHASE 3: BACKEND API (FastAPI)

### 3.1 — Core API Structure

Create `packages/backend/main.py` with these endpoints:
```
POST   /api/trades              — Log a new trade
GET    /api/trades              — List trades (with filters)
GET    /api/trades/{id}         — Get single trade detail
PUT    /api/trades/{id}         — Update trade
DELETE /api/trades/{id}         — Delete trade

GET    /api/analytics/overview       — Dashboard stats
GET    /api/analytics/performance    — Performance over time
GET    /api/analytics/psychology     — Emotion/discipline analysis
GET    /api/analytics/patterns       — Pattern recognition results
GET    /api/analytics/prop-firm      — Prop firm rule compliance

POST   /api/strategies               — Create/update strategy
GET    /api/strategies               — List strategies
POST   /api/backtest                 — Run backtest on strategy
GET    /api/backtest/{id}/results    — Get backtest results

POST   /api/ml/train                 — Train ML model
GET    /api/ml/models                — List trained models
POST   /api/ml/predict               — Get prediction for current market

GET    /api/market/candles           — Get historical candles
GET    /api/market/news              — Get relevant news
GET    /api/market/calendar          — Economic calendar

WS     /ws/market                    — Live market data stream
WS     /ws/signals                   — Real-time trade signals
WS     /ws/sandbox                   — Sandbox trading execution

POST   /api/plan/daily               — Create daily plan
GET    /api/plan/daily/{date}        — Get daily plan
PUT    /api/plan/daily/{date}        — Update daily plan (add review)
```

### 3.2 — Tradovate Connector (Priority #1)

Research and implement the Tradovate API connector:
```
Search: "Tradovate API documentation"
Search: "Tradovate WebSocket API example Python"
Search: "Tradovate API authentication OAuth2"
URL to fetch: https://api.tradovate.com

Key Tradovate API endpoints to implement:
1. Authentication: POST /auth/accesstokenrequest
2. Account info: GET /account/list
3. Positions: GET /position/list
4. Orders: POST /order/placeorder, POST /order/cancelorder
5. Market data: WebSocket subscription for real-time quotes
6. Historical data: GET /md/getChart

Implement TWO modes:
- SANDBOX: Use Tradovate's demo/sim environment (free)
- LIVE: Same code, different API endpoint (when ready)

The connector should:
- Maintain persistent WebSocket connection
- Auto-reconnect on disconnect
- Queue orders when disconnected
- Emit events for: price_update, fill, position_change, account_update
- Log all API calls for debugging
```

---

## PHASE 4: TRADING ENGINE & STRATEGIES

### 4.1 — Strategy Framework

Build an abstract strategy framework where each strategy:
```python
class Strategy(ABC):
    @abstractmethod
    def calculate_indicators(self, candles: pd.DataFrame) -> pd.DataFrame:
        """Add indicator columns to candle dataframe"""
        pass
    
    @abstractmethod
    def generate_signal(self, candles: pd.DataFrame) -> Signal:
        """Return BUY, SELL, or HOLD signal with metadata"""
        pass
    
    @abstractmethod
    def calculate_stop_loss(self, entry_price: float, direction: str) -> float:
        pass
    
    @abstractmethod
    def calculate_take_profit(self, entry_price: float, direction: str) -> float:
        pass
    
    def risk_check(self, account_state: AccountState) -> bool:
        """Check prop firm rules, daily limits, etc."""
        pass
```

### 4.2 — Implement These Strategies (from research)

**Strategy 1: SMC Break & Retest (Raymond's current approach)**
```
- Identify market structure (swing highs/lows)
- Detect BOS (Break of Structure)
- Wait for retest of broken level
- Confirm with VWAP/EMA alignment
- Entry on rejection candle at retest level
- Stop below/above the retest zone
- Target 3:1 R:R
```

**Strategy 2: VWAP Mean Reversion**
```
- Calculate VWAP with 1, 2, 3 standard deviation bands
- Entry when price reaches +/- 2 std dev from VWAP
- Confirmation: RSI divergence, volume climax
- Target: return to VWAP
- Stop: beyond 3 std dev
```

**Strategy 3: Opening Range Breakout (ORB)**
```
- Define opening range (first 15 or 30 min of NY session)
- Break above/below range with volume confirmation
- Entry on breakout or retest of range boundary
- Stop: opposite side of range
- Target: 1.5x or 2x range width
```

**Strategy 4: Order Block + FVG Confluence**
```
- Identify last bullish/bearish candle before impulse move
- Mark Fair Value Gaps (3-candle pattern with gap)
- Enter when price returns to OB + FVG overlap zone
- Requires higher timeframe alignment
```

**Strategy 5: ML Ensemble**
```
- Feature engineering from candles + indicators
- Train XGBoost classifier: UP / DOWN / FLAT
- Use as a FILTER on top of rule-based strategies
- Only take Strategy 1-4 signals when ML agrees
- Walk-forward validation to prevent overfitting
```

**Strategy 6: Reinforcement Learning Agent**
```
- Environment: Gymnasium-compatible trading env
- State: last N candles + indicators + account state
- Actions: BUY, SELL, HOLD, CLOSE
- Reward: Sharpe-adjusted returns with drawdown penalty
- Algorithm: PPO (Proximal Policy Optimization) via stable-baselines3
- CRITICAL: Train on historical data, validate on unseen data
- Track overfitting metrics obsessively
```

### 4.3 — Backtesting Engine

```
Build a robust backtesting engine that:
1. Loads historical candle data from SQLite/DuckDB
2. Runs any Strategy subclass through the data
3. Simulates fills with realistic slippage (0.25-0.5 ticks for MES)
4. Accounts for commissions ($0.62 per side per MES contract on Tradovate)
5. Tracks all prop firm rules during backtest
6. Produces comprehensive statistics:
   - Total P&L, win rate, profit factor
   - Max drawdown, max consecutive losses
   - Sharpe ratio, Sortino ratio, Calmar ratio
   - Expectancy (avg win * win% - avg loss * loss%)
   - R-multiple distribution
   - Performance by: time of day, day of week, session, volatility regime
   - Monte Carlo simulation: 1000 randomized trade sequences
7. Walk-forward optimization:
   - Train on 60 days, test on 5 days, slide forward
   - Report out-of-sample degradation
   - Flag if in-sample >> out-of-sample (overfitting!)
8. Generate visual reports:
   - Equity curve
   - Drawdown chart
   - Win/loss distribution
   - Trade scatter plot (entry time vs P&L)
   - Heat map: P&L by hour of day and day of week
```

---

## PHASE 5: FRONTEND (React + TradingView Charts)

### 5.1 — Core Pages/Views

```
1. DASHBOARD (Home)
   - Today's P&L (big number, color-coded)
   - Prop firm compliance meters (drawdown used, daily loss used)
   - Active positions
   - Today's trade count vs max
   - Win streak / loss streak
   - Quick emotion check-in
   - News ticker for high-impact events
   - ML signal status (if enabled)

2. LIVE CHART
   - TradingView lightweight-charts for price
   - Overlay indicators (VWAP, EMA, Bollinger)
   - Draw key levels from daily plan
   - Mark order blocks, FVGs (detected by engine)
   - Show live signals from active strategies
   - One-click sandbox trade execution
   - Position P&L overlay

3. TRADE JOURNAL
   - Calendar view with daily P&L heat map
   - Trade list with filters (date range, strategy, outcome, emotion)
   - Individual trade detail: chart at entry/exit, notes, lessons
   - Bulk import from Tradovate CSV
   - Quick-add trade form

4. ANALYTICS
   - Performance overview: equity curve, drawdown, key metrics
   - Strategy comparison: side-by-side stats
   - Psychology dashboard:
     * Emotion distribution pie chart
     * P&L by emotion (calm vs FOMO vs revenge)
     * Discipline score over time
     * Rule-following correlation with P&L
   - Pattern analysis:
     * Best/worst time of day
     * Best/worst day of week
     * Performance by setup type
     * Correlation with market conditions
   - Prop firm tracker:
     * Days remaining in evaluation
     * Profit progress bar
     * Drawdown usage visualization
     * Projected pass/fail at current rate

5. STRATEGY LAB
   - Strategy builder (rule-based, visual)
   - Backtest runner with progress bar
   - Results comparison table
   - Walk-forward validation results
   - ML model training interface
   - Paper trade any strategy in real-time

6. MARKET INTEL
   - Economic calendar with impact ratings
   - News feed (filtered for futures-relevant)
   - Key levels from overnight session
   - Sector/index heatmap
   - Options flow / gamma levels (if data available)
   - FRED economic indicators dashboard

7. DAILY PLAN
   - Pre-market template to fill out each morning
   - Key level input (auto-populate from overnight analysis)
   - Bias selection with reasoning
   - Strategy selection for the day
   - Post-session review form with grading
   - Historical plan accuracy tracking

8. SETTINGS
   - Broker connection management
   - Risk parameter configuration
   - Prop firm rule configuration
   - Data source API keys
   - ML model management
   - Theme (dark mode default — traders prefer it)
```

---

## PHASE 6: ML / NEURAL NETWORK PIPELINE

### 6.1 — Feature Engineering

```python
# Generate features from candle data for ML models
def engineer_features(candles: pd.DataFrame) -> pd.DataFrame:
    """
    Input: OHLCV candles
    Output: Feature matrix for ML models
    
    Features to compute:
    
    # Price-based
    - returns_1, returns_5, returns_15, returns_60 (bar returns)
    - log_returns
    - high_low_range / ATR ratio
    - close_position_in_range: (close - low) / (high - low)
    
    # Trend indicators
    - ema_8, ema_20, ema_50 distances from price (normalized by ATR)
    - ema_8_slope, ema_20_slope (rate of change)
    - macd, macd_signal, macd_histogram
    - adx_14
    
    # Mean reversion indicators
    - rsi_14, rsi_7
    - bollinger_band_position: (price - lower) / (upper - lower)
    - vwap_distance (normalized by ATR)
    - vwap_std_position: which std dev band are we in?
    
    # Volume-based
    - volume_ratio: current / 20-bar average
    - volume_trend: 5-bar volume SMA direction
    - delta_volume (if available from order flow)
    - on_balance_volume direction
    
    # Volatility
    - atr_14
    - atr_ratio: atr_14 / atr_50 (expanding or contracting)
    - bollinger_bandwidth
    - keltner_channel_width
    
    # Market structure (SMC-inspired)
    - distance_to_swing_high (normalized)
    - distance_to_swing_low (normalized)
    - bars_since_bos
    - last_bos_direction
    - is_in_fvg: boolean
    - nearest_order_block_distance
    
    # Time features
    - hour_of_day (cyclical encoding: sin + cos)
    - minute_of_hour (cyclical)
    - day_of_week (cyclical)
    - is_kill_zone: london, ny_am, ny_pm
    - minutes_since_market_open
    - is_first_30min
    - is_last_30min
    
    # Economic calendar
    - minutes_until_next_high_impact_event
    - minutes_since_last_high_impact_event
    - is_fomc_day
    - is_nfp_day
    - is_cpi_day
    """
```

### 6.2 — Model Training Pipeline

```
Implement these models with RIGOROUS validation:

1. XGBoost Classifier
   - Target: LONG (+X ticks in N bars), SHORT (-X ticks), FLAT
   - Walk-forward: 60-day train, 5-day test, slide by 5 days
   - Hyperparameter optimization via Optuna
   - Feature importance tracking
   - SHAP values for explainability

2. LSTM Direction Predictor
   - Input: sequence of 60 feature vectors (last 60 bars)
   - Output: probability of up/down in next 5 bars
   - Architecture: 2-layer LSTM, dropout 0.3, dense output
   - Walk-forward validation
   - Learning rate scheduling

3. Regime Detection (Hidden Markov Model)
   - Detect: trending_up, trending_down, ranging, volatile
   - Use regime as context for other strategies
   - Regime-conditional strategy selection

4. Reinforcement Learning Agent
   - Use stable-baselines3 PPO
   - Custom Gymnasium environment simulating MES trading
   - Reward = Sharpe-adjusted returns - drawdown penalty
   - Action masking: prevent trading during restricted times
   - Train on 2 years of 5-min data
   - Evaluate on 6 months unseen data

ANTI-OVERFITTING MEASURES (CRITICAL):
- Always report IN-SAMPLE vs OUT-OF-SAMPLE separately
- Walk-forward validation for all models  
- Monte Carlo permutation test: is the result statistically significant?
- Track model degradation over time
- Implement automatic model retraining triggers
- NEVER deploy a model that only shows in-sample results
- Compare all models against simple baselines (buy-and-hold, random)
- Report confidence intervals, not just point estimates
```

---

## PHASE 7: SANDBOX TRADING ENGINE

### 7.1 — Paper Trading Simulator

```
Build a local sandbox that:
1. Receives real-time market data (from Tradovate demo or delayed feed)
2. Simulates order execution with:
   - Market orders: fill at next bar open + random slippage (0-2 ticks)
   - Limit orders: fill when price crosses limit level
   - Stop orders: fill when price crosses stop level + slippage
3. Tracks account balance, P&L, positions
4. Enforces prop firm rules:
   - Block trades if daily loss limit reached
   - Block trades if max drawdown breached
   - Block trades if max trades/day reached
   - Alert when approaching limits
5. Logs all trades to the journal database
6. Runs strategy signals through the sandbox
7. Can replay historical data at adjustable speed (1x, 5x, 20x, 100x)
8. Generates identical analytics to live trading

Sandbox modes:
- REPLAY: Feed historical data as if it were live (great for practice)
- PAPER: Use real-time data but simulated execution
- HYBRID: Real data, auto-execute signals, but paper P&L
```

---

## PHASE 8: LAUNCH CHECKLIST

```
Before first use:
[ ] Tradovate demo account connected and streaming data
[ ] SQLite database initialized with schema
[ ] At least 60 days of MES 5-min historical data loaded
[ ] SMC Break & Retest strategy coded and backtested
[ ] VWAP Mean Reversion strategy coded and backtested
[ ] Backtest results documented with walk-forward validation
[ ] Dashboard showing real-time P&L and prop firm compliance
[ ] Trade journal with manual entry working
[ ] Daily plan template working
[ ] Sandbox paper trading executing correctly
[ ] Risk management rules enforced in sandbox

Before enabling live:
[ ] Minimum 30 days of profitable sandbox trading
[ ] Walk-forward validated strategy with positive expectancy
[ ] All prop firm rules properly enforced
[ ] Kill switch: one-click to flatten all positions
[ ] Maximum loss circuit breaker tested
[ ] Tradovate live API credentials configured (separate from demo)
```

---

## PHASE 9: DEVELOPMENT ORDER (Suggested Sprint Plan)

```
Sprint 1 (Days 1-3): Foundation
- Project scaffolding
- SQLite schema & database setup
- FastAPI skeleton with trade CRUD endpoints
- Basic React frontend with routing
- Dark theme setup with Tailwind

Sprint 2 (Days 4-7): Data & Charts
- Historical data loader (Databento or free source)
- TradingView lightweight-charts integration
- Candle data display with VWAP + EMA overlay
- Basic indicator calculations (pandas-ta)

Sprint 3 (Days 8-11): Trading Journal Core
- Trade entry form (manual)
- Trade list with filtering
- Calendar heat map view
- Basic analytics: win rate, P&L curve, profit factor
- CSV import from Tradovate

Sprint 4 (Days 12-16): Backtesting Engine
- Strategy framework (abstract class)
- Implement SMC Break & Retest strategy
- Implement VWAP Mean Reversion strategy
- Backtesting engine with realistic fills
- Walk-forward validation
- Backtest results visualization

Sprint 5 (Days 17-21): Broker Connection
- Tradovate API connector (demo/sandbox)
- Real-time WebSocket data streaming
- Sandbox paper trading execution
- Position tracking & P&L calculation
- Prop firm rule enforcement

Sprint 6 (Days 22-26): ML Pipeline
- Feature engineering pipeline
- XGBoost model training + walk-forward
- LSTM model training + validation
- Regime detection (HMM)
- Signal integration with strategies
- Model performance dashboard

Sprint 7 (Days 27-30): Polish & Intelligence
- Daily plan workflow
- Psychology/emotion tracking
- News integration (Finnhub or similar)
- Economic calendar integration
- Pattern analysis (best times, conditions)
- Performance reporting

Sprint 8 (Days 31+): Advanced
- RL agent training
- Multi-strategy ensemble
- Auto-parameter optimization
- Trade replay simulator
- Tauri desktop packaging (optional)
- Auto-update mechanism
```

---

## KEY REMINDERS

```
1. ALWAYS START WITH RESEARCH — Don't code until you understand the
   Tradovate API, the data sources, and the strategy mechanics deeply.

2. SANDBOX FIRST — Never connect live trading until 30+ days of
   profitable sandbox results with proper walk-forward validation.

3. ANTI-OVERFITTING IS EVERYTHING — The #1 reason ML trading strategies
   fail is overfitting. Walk-forward validate EVERYTHING. Compare
   against random baselines. Report out-of-sample results only.

4. RISK MANAGEMENT > SIGNAL GENERATION — A mediocre strategy with
   great risk management will outperform a great strategy with
   poor risk management. The prop firm rules ARE your edge.

5. PSYCHOLOGY IS THE REAL EDGE — Track emotions, discipline, plan
   adherence. The data will show that following your rules is more
   important than which rules you follow.

6. KEEP COSTS MINIMAL — Use free APIs where possible. Tradovate demo
   is free. Databento is pay-per-use. Most indicators are computed
   locally. The only costs should be data feeds.

7. BUILD FOR YOURSELF FIRST — You are the ideal user. Make it solve
   YOUR problems. Then productize later.

8. GIT VERSION EVERYTHING — Strategies, configs, model weights,
   trade data. You need to reproduce any result at any point in time.
```

---

## APPENDIX: Research URLs to Visit

```
# Tradovate API
https://api.tradovate.com
https://github.com/nicholasgasior/tradovate-api  (search for community SDKs)

# Market Data
https://databento.com/docs
https://polygon.io/docs/stocks
https://finnhub.io/docs/api

# Charting
https://tradingview.github.io/lightweight-charts/

# Backtesting
https://vectorbt.dev/
https://www.backtrader.com/docu/

# ML for Trading
https://github.com/stefan-jansen/machine-learning-for-trading
https://github.com/AI4Finance-Foundation/FinRL

# RL for Trading
https://stable-baselines3.readthedocs.io/
https://github.com/AI4Finance-Foundation/FinRL

# Trading Strategy Research
Search: "quantified SMC trading strategy results"
Search: "VWAP trading strategy backtest futures"
Search: "order flow trading edge statistical evidence"
Search: "prop firm evaluation strategy optimization"
Search: "walk forward analysis trading python"

# Economics
https://fred.stlouisfed.org/docs/api/
```
