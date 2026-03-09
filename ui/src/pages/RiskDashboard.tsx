import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Shield, AlertTriangle, TrendingDown, Activity } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";

function Gauge({ label, value, max, unit = "$", danger = 0.75, critical = 0.9 }: any) {
  const pct = Math.min(value / max, 1);
  const color = pct >= critical ? "text-red-400" : pct >= danger ? "text-amber-400" : "text-emerald-400";
  const barColor = pct >= critical ? "bg-red-500" : pct >= danger ? "bg-amber-500" : "bg-emerald-500";

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs text-gray-400">{label}</span>
        <span className={`text-sm font-bold ${color}`}>{unit}{value.toFixed(0)}</span>
      </div>
      <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all duration-500`}
             style={{ width: `${pct * 100}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-gray-600 mt-1">
        <span>{unit}0</span>
        <span>{unit}{max}</span>
      </div>
    </div>
  );
}

export default function RiskDashboard() {
  const { data: risk } = useQuery({ queryKey: ["risk"], queryFn: api.getRisk });
  const { data: equity } = useQuery({ queryKey: ["equity"], queryFn: api.getEquityCurve });
  const { data: overview } = useQuery({ queryKey: ["overview"], queryFn: api.getOverview });

  const r = risk || {
    balance: 50000, peak_balance: 50000, drawdown: 0, drawdown_pct: 0,
    max_loss_floor: 48000, distance_to_max_loss: 2000, daily_pnl: 0,
    daily_trades: 0, consecutive_losses: 0, pdll: 200, pdpt: 300,
    pdll_remaining: 200, pdpt_remaining: 300, should_halt: false,
  };

  const equityData = (equity?.equity || [50000]).map((v: number, i: number) => ({
    idx: i, balance: v,
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-cyan-400" />
          <h1 className="text-xl font-bold">Risk Dashboard</h1>
        </div>
        {r.should_halt && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-red-500/20 border border-red-500/30 rounded-lg pulse-glow">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <span className="text-sm text-red-400 font-bold">TRADING HALTED</span>
          </div>
        )}
      </div>

      {/* Gauges */}
      <div className="grid grid-cols-4 gap-3">
        <Gauge label="Trailing Drawdown" value={r.drawdown} max={2000} danger={0.6} critical={0.85} />
        <Gauge label="Daily Loss Used" value={Math.abs(Math.min(r.daily_pnl, 0))} max={r.pdll} />
        <Gauge label="Daily Profit" value={Math.max(r.daily_pnl, 0)} max={r.pdpt} danger={0.9} critical={1.0} />
        <Gauge label="Trades Today" value={r.daily_trades} max={3} unit="" />
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-5 gap-3">
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
          <div className="text-xs text-gray-500">Balance</div>
          <div className="text-lg font-bold text-cyan-400">${r.balance.toFixed(2)}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
          <div className="text-xs text-gray-500">Peak Balance</div>
          <div className="text-lg font-bold text-gray-200">${r.peak_balance.toFixed(2)}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
          <div className="text-xs text-gray-500">Max Loss Floor</div>
          <div className="text-lg font-bold text-red-400">${r.max_loss_floor.toFixed(0)}</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
          <div className="text-xs text-gray-500">Distance to Ruin</div>
          <div className={`text-lg font-bold ${r.distance_to_max_loss < 500 ? "text-red-400" : "text-emerald-400"}`}>
            ${r.distance_to_max_loss.toFixed(0)}
          </div>
        </div>
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
          <div className="text-xs text-gray-500">Consec. Losses</div>
          <div className={`text-lg font-bold ${r.consecutive_losses >= 2 ? "text-red-400" : "text-gray-200"}`}>
            {r.consecutive_losses}
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Equity Curve</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={equityData}>
            <XAxis dataKey="idx" tick={false} />
            <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#6b7280" }} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1a2332", border: "1px solid #243044", borderRadius: 8 }}
              labelStyle={{ color: "#9ca3af" }}
            />
            <ReferenceLine y={50000} stroke="#374151" strokeDasharray="3 3" />
            <ReferenceLine y={48000} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "Max Loss", fill: "#ef4444", fontSize: 10 }} />
            <Line type="monotone" dataKey="balance" stroke="#06b6d4" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
