// API URL resolution:
// - In Vite dev: proxied through /api -> localhost:8000
// - In Tauri/production: VITE_API_URL env var points to EC2 backend
const API_URL = import.meta.env.VITE_API_URL || "";
const API_BASE = `${API_URL}/api`;

// WebSocket URL for live data
export const WS_URL = import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/live`;

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postApi<T>(path: string, body: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export interface OverviewStats {
  total_pnl: number;
  today_pnl: number;
  total_trades: number;
  today_trades: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  account_balance: number;
  pdll_used: number;
  pdpt_progress: number;
  max_loss_distance: number;
  scaling_contracts: number;
  mode: string;
  current_regime: string;
  regime_confidence: number;
}

export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  is_active: boolean;
  preferred_regimes: string[];
  weight: number;
  total_signals: number;
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  sharpe: number;
  status: string;
}

export interface TradeRecord {
  id: string;
  ts_open: string;
  ts_close: string | null;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  pnl: number | null;
  agent_signals: string[];
  regime: string;
  mode: string;
}

export interface BacktestResult {
  agent_id: string;
  oos_total_trades: number;
  oos_win_rate: number;
  oos_profit_factor: number;
  oos_sharpe: number;
  oos_max_drawdown: number;
  oos_expectancy: number;
  wf_num_windows: number;
  wf_pct_profitable_windows: number;
  p_value: number;
  is_significant: boolean;
  mc_probability_of_ruin: number;
  equity_curve: number[];
}

export interface CandleData {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface RiskStatus {
  balance: number;
  peak_balance: number;
  drawdown: number;
  drawdown_pct: number;
  max_loss_floor: number;
  distance_to_max_loss: number;
  daily_pnl: number;
  daily_trades: number;
  consecutive_losses: number;
  pdll: number;
  pdpt: number;
  pdll_remaining: number;
  pdpt_remaining: number;
  should_halt: boolean;
}

export const api = {
  getHealth: () => fetchApi<any>("/health"),
  getOverview: () => fetchApi<OverviewStats>("/overview"),
  getAgents: () => fetchApi<AgentStatus[]>("/agents"),
  getAgent: (id: string) => fetchApi<any>(`/agents/${id}`),
  getTrades: (limit = 50) => fetchApi<TradeRecord[]>(`/trades?limit=${limit}`),
  getCandles: (limit = 500) => fetchApi<CandleData[]>(`/candles?limit=${limit}`),
  getFeatures: (limit = 100) => fetchApi<any[]>(`/features?limit=${limit}`),
  getRegime: () => fetchApi<any>("/regime"),
  getRisk: () => fetchApi<RiskStatus>("/risk"),
  getEquityCurve: () => fetchApi<{ equity: number[] }>("/equity-curve"),
  getConfig: () => fetchApi<any>("/config"),
  runBacktest: (params: any) => postApi<BacktestResult>("/backtest", params),
};
