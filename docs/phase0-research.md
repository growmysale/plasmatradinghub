# PropEdge v2 - Phase 0 Research Document
## Deep Research Findings for the Adaptive Neural Trading System

---

## 1. HOW QUANTITATIVE HEDGE FUNDS ACTUALLY WORK

### 1.1 Renaissance Technologies / Medallion Fund Model

RenTech's approach that we're replicating at micro scale:

- **Signal Factory**: Hundreds of weak alpha signals (each 51-53% accurate) are combined into one strong composite signal using statistical techniques. No single signal is relied upon.
- **Feature Engineering Over Model Complexity**: RenTech spends more time on data quality and feature engineering than model architecture. Clean, denoised features matter more than fancy models.
- **Regime Awareness**: The system continuously detects market regimes and adjusts which signals get weight. Trend-following signals are upweighted during trending markets; mean-reversion signals during ranging.
- **Walk-Forward Everything**: Every model is validated out-of-sample via walk-forward analysis. In-sample performance is considered meaningless.
- **Position Sizing = Edge Management**: Kelly Criterion (usually quarter-Kelly) determines bet size based on confidence. Higher confidence = larger position, but never more than risk limits allow.
- **Execution Quality Obsession**: Even on liquid instruments, slippage compounds. Their backtests model realistic fills, slippage, and market impact.

### 1.2 Multi-Strategy Pod Structure (Citadel/Two Sigma Model)

- Each "pod" (strategy agent) operates independently with its own P&L
- Pods compete for capital allocation based on risk-adjusted returns
- Poor-performing pods have capital reduced or are shut down entirely
- New pods are constantly incubated and tested
- A central risk management layer sits above all pods

**Our implementation**: 5+ strategy agents (SMC, VWAP MR, ORB, OB+FVG, Momentum) each as independent pods, with the Allocator serving as portfolio manager and Risk Manager as the overarching governor.

### 1.3 Key Architectural Patterns

| Pattern | Institution | Our Implementation |
|---------|-----------|-------------------|
| Signal Combination | Weighted ensemble | Allocator with weighted_vote / regime_conditional |
| Risk Overlay | Central risk desk | RiskManager 6-stage pipeline |
| Position Sizing | Kelly Criterion | Quarter-Kelly with fixed fractional fallback |
| Strategy Selection | Performance-based allocation | OOS Sharpe-weighted agent weights |
| Regime Detection | HMM / clustering | GaussianHMM with 5 states |
| Backtesting | Walk-forward validation | Sliding window train/test with Monte Carlo |

---

## 2. REGIME DETECTION

### 2.1 Hidden Markov Model Approach

Our HMM classifies 5 market states:
- **TRENDING_UP**: High ADX (>25), positive returns autocorrelation, directional momentum
- **TRENDING_DOWN**: High ADX, negative returns, selling pressure
- **RANGING**: Low ADX (<20), returns oscillate around zero, mean-reverting behavior
- **VOLATILE_EXPANSION**: High ATR percentile (>75th), Bollinger bandwidth expanding, VIX elevated
- **QUIET_COMPRESSION**: Low ATR percentile (<25th), Bollinger squeeze, pre-breakout conditions

### 2.2 Features Fed to HMM
- ATR percentile (14-bar ATR ranked over 60-bar window)
- ATR rate of change (volatility expanding or contracting)
- ADX value (trend strength)
- Bollinger bandwidth (volatility proxy)
- Returns autocorrelation (trending = positive, MR = negative)
- Volume ratio (current vs 20-bar average)

### 2.3 Strategy-Regime Mapping

| Regime | Active Agents | Risk Scaling |
|--------|--------------|-------------|
| TRENDING_UP | SMC B&R, Momentum, ORB | 1.0x (full risk) |
| TRENDING_DOWN | SMC B&R, Momentum, OB+FVG | 0.8x |
| RANGING | VWAP MR, OB+FVG | 0.7x |
| VOLATILE_EXPANSION | ORB, Momentum | 0.5x (reduced) |
| QUIET_COMPRESSION | VWAP MR | 0.3x (minimal) |

---

## 3. WALK-FORWARD VALIDATION (Non-Negotiable)

### 3.1 Why Overfitting Is The #1 Killer

- If in-sample Sharpe = 3.0 but out-of-sample Sharpe = 0.3, the strategy is garbage
- Indicators with many parameters (e.g., neural nets) overfit easily
- The more parameters tuned, the higher the overfitting risk
- Solution: ALWAYS evaluate on unseen data

### 3.2 Our Walk-Forward Protocol

```
Day 1-60:     [=====TRAIN=====]
Day 61-65:                      [=TEST=]  -> Record OOS metrics
Day 6-65:      [=====TRAIN=====]
Day 66-70:                       [=TEST=]  -> Record OOS metrics
... slide forward by test_days ...
```

- Train window: 30-60 days (configurable)
- Test window: 5 days (1 trading week)
- Minimum 30 OOS trades for statistical significance
- T-test against zero returns (p < 0.05)

### 3.3 Significance Testing

- **T-test**: Are OOS returns statistically different from zero?
- **Monte Carlo**: Shuffle trade order 1000x, calculate probability of ruin
- **Consistency**: What % of walk-forward windows are profitable?
- A strategy must pass ALL three to be promoted from sandbox to paper trading

---

## 4. KELLY CRITERION & POSITION SIZING

### 4.1 Formula
```
Kelly % = (win_prob * avg_win - loss_prob * avg_loss) / avg_win
```

### 4.2 Application for MES Futures
- Full Kelly is too aggressive (huge drawdowns)
- **Quarter-Kelly** is our default: `size = Kelly% / 4`
- For MES with $50 max risk: position size = min(Kelly-sized, risk-limited)
- Example: 60% win rate, 3:1 R:R -> Kelly = 0.467 -> Quarter-Kelly = 0.117 -> ~$5,850 risk -> 1-2 MES contracts

### 4.3 TopstepX Scaling Plan
| Profit Level | Max Contracts |
|-------------|--------------|
| $0 - $999 | 2 |
| $1,000 - $1,999 | 4 |
| $2,000 - $2,999 | 6 |
| $3,000+ | 10 |

---

## 5. DATA SOURCES & BROKER APIS

### 5.1 Tradovate API (Primary - TopstepX Execution Platform)

**Authentication**:
- OAuth2 access token flow via POST `/auth/accesstokenrequest`
- Requires: username, password, appId, appVersion, cid (client ID), sec (client secret)
- Token has expiration time, auto-refresh before expiry
- Demo environment: `https://demo.tradovateapi.com/v1` (free sandbox)
- Live environment: `https://live.tradovateapi.com/v1`

**REST API Endpoints**:
- `GET /account/list` - List accounts
- `GET /position/list` - Open positions
- `POST /order/placeOrder` - Place orders (Market, Limit, Stop, StopLimit)
- `POST /order/cancelOrder` - Cancel orders
- `GET /cashBalance/getCashBalanceSnapshot` - Account balance
- `GET /contract/find?name=MESM5` - Find contract by symbol

**WebSocket Market Data** (`wss://md-d.tradovateapi.com/v1/websocket`):
- Authorize with access token
- Subscribe to quotes: `md/subscribeQuote` with symbol
- Subscribe to DOM: `md/subscribeDOM` with symbol
- Get chart data: `md/getChart` with symbol + timeframe config
- Message format: `endpoint\nrequestId\n\njsonPayload`

**Key Notes**:
- Demo environment is FREE and fully functional for paper trading
- Rate limits: ~5 requests/second for REST, no explicit WS limit
- Contract symbols change quarterly: MESH5, MESM5, MESU5, MESZ5
- WebSocket reconnection needed on token refresh

### 5.2 Historical Data Sources

| Source | Coverage | Quality | Cost | Format |
|--------|----------|---------|------|--------|
| **Databento** | Tick/minute CME data | Gold standard | $0.01-0.03/instrument-day | Python SDK, binary |
| **Polygon.io** | Futures, stocks | Good | $99-199/mo | REST API, WebSocket |
| **FirstRateData** | ES/MES historical | Good | ~$50 one-time | CSV download |
| **Kibot** | ES historical (free samples) | Adequate | Free-$300 | CSV |
| **Yahoo Finance** | ES continuous (/ES=F) | Low (daily only) | Free | yfinance Python |

**Recommendation**: Start with Kibot/FirstRateData CSV for backtesting (cheap), use Tradovate demo for real-time, upgrade to Databento when ready for production.

### 5.3 Macro / Alternative Data

| Source | Data | Cost | API |
|--------|------|------|-----|
| **FRED** (St. Louis Fed) | Fed funds rate, CPI, GDP, unemployment, yield curves | Free | `fredapi` Python |
| **Finnhub** | Economic calendar, market news, earnings | Free tier: 60 calls/min | REST API |
| **CFTC COT** | Commitment of Traders positioning | Free | Weekly CSV / Quandl |
| **VIX** | CBOE volatility index | Free via Yahoo | yfinance |

---

## 6. EXECUTION QUALITY

### 6.1 Realistic Backtest Assumptions for MES

| Parameter | Conservative | Aggressive |
|-----------|-------------|-----------|
| Slippage per side | 0.50 ticks ($0.625) | 0.25 ticks ($0.3125) |
| Commission per side | $0.62 (Tradovate) | $0.00 (TopstepX) |
| Fill rate (limits) | 70% | 85% |
| Market impact | Negligible for 1-2 contracts | Negligible |

### 6.2 MES Contract Specifications
- Tick size: 0.25 index points
- Tick value: $1.25
- Point value: $5.00
- Trading hours: Sun 6pm - Fri 5pm ET (23/5)
- Initial margin: ~$1,500 (varies)
- Day trade margin: ~$50-100 (TopstepX)

### 6.3 TopstepX $50K Combine Rules
- **Trailing Max Loss**: $2,000 (trails from peak equity)
- **Profit Target**: $3,000 to pass combine
- **Consistency Rule**: Best day < 50% of total profit
- **No overnight positions** (must be flat by 4:59 PM ET)
- **Commission-free trading** on TopstepX
- **Daily reset**: No daily loss limit from TopstepX (we enforce our own PDLL)

---

## 7. SYSTEM ARCHITECTURE: PROPEDGE v2

### 7.1 Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   RAYMOND'S LAPTOP                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         TAURI DESKTOP APP (PropEdge)             │   │
│  │  ┌──────────────────────────────────────────┐    │   │
│  │  │     React Frontend (Observation Deck)    │    │   │
│  │  │  - Command Center                        │    │   │
│  │  │  - Live Chart (TradingView)              │    │   │
│  │  │  - Agent Deep Dive                       │    │   │
│  │  │  - Risk Dashboard                        │    │   │
│  │  │  - Backtest Center                       │    │   │
│  │  │  - Trade Journal                         │    │   │
│  │  │  - Settings                              │    │   │
│  │  └──────────────┬───────────────────────────┘    │   │
│  │                 │ HTTPS/WSS                       │   │
│  └─────────────────┼────────────────────────────────┘   │
│                    │                                     │
└────────────────────┼─────────────────────────────────────┘
                     │
                     │ Internet
                     │
┌────────────────────┼─────────────────────────────────────┐
│                EC2 INSTANCE                               │
│                    │                                      │
│  ┌─────────────────┼────────────────────────────────┐    │
│  │           Docker Container                        │    │
│  │                 │                                 │    │
│  │  ┌──────────────┴───────────────────────────┐    │    │
│  │  │     FastAPI Backend (PropEdge Engine)     │    │    │
│  │  │                                           │    │    │
│  │  │  Layer 0: Data Infra (DuckDB + SQLite)   │    │    │
│  │  │  Layer 1: Feature Engine (80 features)   │    │    │
│  │  │  Layer 2: Strategy Agents (5+ agents)    │    │    │
│  │  │  Layer 3: Allocator (weighted vote)      │    │    │
│  │  │  Layer 4: Risk Manager (6-stage pipe)    │    │    │
│  │  │  Layer 5: Execution Engine               │    │    │
│  │  │  ┌─────────────────────────────────┐     │    │    │
│  │  │  │    Tradovate WebSocket Client   │     │    │    │
│  │  │  │    (Real-time MES data + orders)│     │    │    │
│  │  │  └─────────────────────────────────┘     │    │    │
│  │  └──────────────────────────────────────────┘    │    │
│  │                                                   │    │
│  │  Volume: /data (DuckDB, SQLite, models, logs)    │    │
│  └───────────────────────────────────────────────────┘    │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 7.2 Development Workflow

| Command | What it does |
|---------|-------------|
| `make dev` | Start FastAPI backend + React UI locally |
| `make dev-backend` | Start only Python backend with hot reload |
| `make dev-frontend` | Start only React/Vite dev server |
| `make tauri-dev` | Start Tauri desktop app in dev mode |
| `make build` | Build Docker image + frontend assets |
| `make deploy` | Full deploy: build, transfer, restart on EC2 |
| `make deploy-quick` | Quick deploy: rsync code + restart on EC2 |
| `make logs` | Tail EC2 container logs |
| `make ssh` | SSH into EC2 instance |

### 7.3 Technology Stack

**Backend (Python)**:
- FastAPI + Uvicorn (async API server)
- DuckDB (analytics warehouse)
- SQLite (operational state)
- NumPy/Pandas (data processing)
- scikit-learn, XGBoost, hmmlearn (ML)
- Gymnasium (RL environment)

**Frontend (TypeScript/React)**:
- React 19 + React Router 7
- TanStack Query (data fetching with auto-refresh)
- TradingView Lightweight Charts v5
- Recharts (equity curves, bar charts)
- Tailwind CSS v4 (dark theme)
- Zustand (state management)
- Lucide React (icons)

**Desktop (Rust)**:
- Tauri v2 (native desktop wrapper)
- Targets: Windows (primary), macOS (secondary)

**Infrastructure**:
- Docker (containerized backend)
- EC2 (production hosting, 24/7 headless)
- Makefile (build automation)
- rsync (quick deployment)

---

## 8. PERSONAL RISK MANAGEMENT (Raymond's Rules)

### 8.1 Non-Negotiable Limits

| Rule | Value | Enforcement |
|------|-------|------------|
| Personal Daily Loss Limit (PDLL) | $200 | Hard stop, all trading halts |
| Personal Daily Profit Target (PDPT) | $300 | Trading halts, protect gains |
| Max risk per trade | $50 | Position sizing capped |
| Max trades per day | 3 | Counter increments, blocks new signals |
| Min risk:reward | 2:1 | Signal rejected if R:R < 2 |
| Cooldown after 2 consecutive losses | 15 min | Timer-based lockout |
| News blackout | 5 min before/after | Economic calendar integration |
| No overnight positions | Flatten by 4:59 PM ET | Automatic flatten |

### 8.2 Circuit Breakers (Auto-Triggered)

1. **Daily P&L Circuit Breaker**: If daily P&L hits -$200, all trading stops
2. **Consecutive Loss Circuit Breaker**: After 2 consecutive losses, 15-min cooldown
3. **Drawdown Circuit Breaker**: If trailing drawdown > $1,500, reduce to minimum sizing
4. **Regime Uncertainty Breaker**: If regime confidence < 50%, reduce risk by 50%

---

## 9. NEXT STEPS (Implementation Priorities)

### Phase 1: Foundation (DONE)
- [x] Core types, config, event bus
- [x] DuckDB + SQLite schema
- [x] Candle store with sample data generation

### Phase 2: Feature Engine (DONE)
- [x] 80 features across 8 categories
- [x] HMM regime detection (5 states)
- [x] Custom indicator library (no pandas-ta dependency)

### Phase 3: Strategy Agents (DONE)
- [x] 5 rule-based agents (SMC, VWAP MR, ORB, OB+FVG, Momentum)
- [x] XGBoost classifier agent
- [x] RL PPO agent skeleton
- [x] Agent registry system

### Phase 4: Infrastructure (DONE)
- [x] Walk-forward backtester with Monte Carlo
- [x] Allocator with 3 combination methods
- [x] Risk Manager 6-stage pipeline
- [x] Execution engine (sandbox/paper/live)
- [x] Genetic evolution engine

### Phase 5: API + Frontend (DONE)
- [x] FastAPI REST + WebSocket API
- [x] React Observation Deck (7 pages)
- [x] All endpoints verified working

### Phase 6: Deployment Architecture (DONE)
- [x] Dockerfile for EC2 deployment
- [x] docker-compose for dev + production
- [x] Makefile with all targets
- [x] Tauri v2 desktop app scaffold
- [x] Tradovate API client
- [x] Environment configuration (.env)

### Phase 7: Next Priorities
- [ ] Load real MES historical data (Kibot/FirstRateData CSV)
- [ ] Run full walk-forward backtests on real data
- [ ] Connect to Tradovate demo for paper trading
- [ ] Train XGBoost on real data features
- [ ] Build Tauri desktop app (requires Rust toolchain)
- [ ] Deploy backend to EC2
- [ ] Set up HTTPS/SSL for EC2 API (Let's Encrypt or AWS ACM)
- [ ] Implement background learning loop (continuous backtesting)
- [ ] Add economic calendar integration (Finnhub)
- [ ] Add FRED macro data for regime detection

---

*Document generated: March 2026*
*PropEdge v2.0.0 - Adaptive Neural Trading System*
