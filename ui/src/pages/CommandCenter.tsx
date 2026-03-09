import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  Activity, TrendingUp, TrendingDown, AlertTriangle, Shield,
  Zap, Target, BarChart3, Clock, Users,
} from "lucide-react";

function StatCard({ label, value, sub, icon: Icon, color = "text-gray-100" }: any) {
  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-500">{label}</span>
        {Icon && <Icon className={`w-4 h-4 ${color}`} />}
      </div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function ProgressBar({ value, max, color = "bg-cyan-500", label }: any) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-300">${value.toFixed(0)} / ${max}</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RegimeBadge({ regime, confidence }: { regime: string; confidence: number }) {
  const colors: Record<string, string> = {
    trending_up: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    trending_down: "bg-red-500/20 text-red-400 border-red-500/30",
    ranging: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    volatile_expansion: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    quiet_compression: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    unknown: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${colors[regime] || colors.unknown}`}>
      <Activity className="w-3 h-3" />
      {regime.replace("_", " ").toUpperCase()} ({(confidence * 100).toFixed(0)}%)
    </span>
  );
}

function AgentStatusRow({ agent }: any) {
  const weightPct = (agent.weight * 100).toFixed(0);
  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-800 last:border-0">
      <div className="w-20 text-xs font-mono text-cyan-400">{agent.agent_id}</div>
      <div className="flex-1">
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-cyan-500 rounded-full" style={{ width: `${weightPct}%` }} />
        </div>
      </div>
      <div className="text-xs text-gray-400 w-16 text-right">{weightPct}% wt</div>
      <div className={`text-xs px-1.5 py-0.5 rounded ${agent.is_active ? "bg-emerald-500/20 text-emerald-400" : "bg-gray-700 text-gray-500"}`}>
        {agent.is_active ? "ACTIVE" : "PAUSED"}
      </div>
    </div>
  );
}

export default function CommandCenter() {
  const { data: overview } = useQuery({ queryKey: ["overview"], queryFn: api.getOverview });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const { data: risk } = useQuery({ queryKey: ["risk"], queryFn: api.getRisk });

  const o = overview || {
    total_pnl: 0, today_pnl: 0, total_trades: 0, today_trades: 0,
    win_rate: 0, profit_factor: 0, max_drawdown: 0, account_balance: 50000,
    pdll_used: 0, pdpt_progress: 0, max_loss_distance: 2000,
    scaling_contracts: 2, mode: "sandbox", current_regime: "unknown",
    regime_confidence: 0,
  };

  const r = risk || {
    balance: 50000, drawdown: 0, distance_to_max_loss: 2000,
    daily_pnl: 0, daily_trades: 0, pdll: 200, pdpt: 300,
    pdll_remaining: 200, pdpt_remaining: 300, should_halt: false,
  };

  const pnlColor = o.today_pnl >= 0 ? "text-emerald-400" : "text-red-400";
  const pnlIcon = o.today_pnl >= 0 ? TrendingUp : TrendingDown;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Command Center</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
              o.mode === "live" ? "bg-red-500/20 text-red-400" :
              o.mode === "paper" ? "bg-amber-500/20 text-amber-400" :
              "bg-cyan-500/20 text-cyan-400"
            }`}>
              <Zap className="w-3 h-3" />
              {o.mode.toUpperCase()}
            </span>
            <RegimeBadge regime={o.current_regime} confidence={o.regime_confidence} />
            <span className="text-xs text-gray-500">MES | {o.scaling_contracts} contracts</span>
          </div>
        </div>
        {r.should_halt && (
          <div className="flex items-center gap-2 px-3 py-2 bg-red-500/20 border border-red-500/30 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <span className="text-sm text-red-400 font-semibold">TRADING HALTED</span>
          </div>
        )}
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Today's P&L" value={`$${o.today_pnl.toFixed(2)}`}
          sub={`${o.today_trades}/3 trades`} icon={pnlIcon} color={pnlColor} />
        <StatCard label="Account Balance" value={`$${o.account_balance.toFixed(2)}`}
          sub={`Peak: $${(r.balance + r.drawdown).toFixed(0)}`} icon={Target} color="text-cyan-400" />
        <StatCard label="Total P&L" value={`$${o.total_pnl.toFixed(2)}`}
          sub={`${o.total_trades} trades | WR: ${(o.win_rate * 100).toFixed(1)}%`}
          icon={BarChart3} color={o.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"} />
        <StatCard label="Max Loss Distance" value={`$${o.max_loss_distance.toFixed(0)}`}
          sub={`Drawdown: $${r.drawdown.toFixed(0)}`} icon={Shield}
          color={o.max_loss_distance < 500 ? "text-red-400" : o.max_loss_distance < 1000 ? "text-amber-400" : "text-emerald-400"} />
      </div>

      {/* Risk Gauges + Agent Status */}
      <div className="grid grid-cols-3 gap-4">
        {/* Risk Gauges */}
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Shield className="w-4 h-4 text-cyan-400" /> Prop Firm Compliance
          </h3>
          <ProgressBar value={r.drawdown} max={2000} color="bg-red-500" label="Trailing Max Loss" />
          <ProgressBar value={o.pdll_used} max={200}
            color={o.pdll_used > 150 ? "bg-red-500" : o.pdll_used > 100 ? "bg-amber-500" : "bg-emerald-500"}
            label="Daily Loss Limit (PDLL)" />
          <ProgressBar value={o.pdpt_progress} max={300} color="bg-emerald-500" label="Daily Profit Target (PDPT)" />
          <div className="flex justify-between text-xs text-gray-500 mt-2">
            <span>Profit Factor: {o.profit_factor.toFixed(2)}</span>
            <span>Max DD: ${o.max_drawdown.toFixed(0)}</span>
          </div>
        </div>

        {/* Agent Status */}
        <div className="col-span-2 bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-cyan-400" /> Agent Status
          </h3>
          <div className="space-y-0">
            {(agents || []).map((agent: any) => (
              <AgentStatusRow key={agent.agent_id} agent={agent} />
            ))}
            {(!agents || agents.length === 0) && (
              <div className="text-xs text-gray-600 py-4 text-center">Loading agents...</div>
            )}
          </div>
        </div>
      </div>

      {/* System Info Footer */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-gray-900/50 rounded p-3 border border-gray-800/50 text-center">
          <div className="text-xs text-gray-500">Win Rate</div>
          <div className="text-lg font-bold text-gray-200">{(o.win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-gray-900/50 rounded p-3 border border-gray-800/50 text-center">
          <div className="text-xs text-gray-500">Profit Factor</div>
          <div className="text-lg font-bold text-gray-200">{o.profit_factor.toFixed(2)}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-3 border border-gray-800/50 text-center">
          <div className="text-xs text-gray-500">Regime</div>
          <div className="text-sm font-bold text-cyan-400">{o.current_regime.replace("_", " ").toUpperCase()}</div>
        </div>
        <div className="bg-gray-900/50 rounded p-3 border border-gray-800/50 text-center">
          <div className="text-xs text-gray-500">Consecutive Losses</div>
          <div className={`text-lg font-bold ${(r.consecutive_losses || 0) >= 2 ? "text-red-400" : "text-gray-200"}`}>
            {r.consecutive_losses || 0}
          </div>
        </div>
      </div>
    </div>
  );
}
