import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, BacktestResult } from "../lib/api";
import { FlaskConical, Play, CheckCircle, XCircle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";

export default function BacktestCenter() {
  const [selectedAgent, setSelectedAgent] = useState("smc_br");
  const [days, setDays] = useState(60);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });

  const mutation = useMutation({
    mutationFn: (params: any) => api.runBacktest(params),
    onSuccess: (data) => setResult(data),
  });

  const runBacktest = () => {
    mutation.mutate({
      agent_id: selectedAgent,
      days,
      walk_forward: true,
      train_days: 30,
      test_days: 5,
    });
  };

  const equityData = result?.equity_curve?.map((v, i) => ({ idx: i, balance: v })) || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FlaskConical className="w-5 h-5 text-cyan-400" />
        <h1 className="text-xl font-bold">Backtest Center</h1>
      </div>

      {/* Controls */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 flex items-end gap-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Agent</label>
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="bg-gray-800 text-gray-200 rounded px-3 py-2 text-sm border border-gray-700"
          >
            {(agents || []).map((a: any) => (
              <option key={a.agent_id} value={a.agent_id}>{a.agent_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Days</label>
          <input
            type="number" value={days} onChange={(e) => setDays(+e.target.value)}
            className="bg-gray-800 text-gray-200 rounded px-3 py-2 text-sm border border-gray-700 w-24"
          />
        </div>
        <button
          onClick={runBacktest}
          disabled={mutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-500 text-gray-950 rounded font-semibold text-sm hover:bg-cyan-400 disabled:opacity-50"
        >
          <Play className="w-4 h-4" />
          {mutation.isPending ? "Running..." : "Run Walk-Forward"}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-6 gap-3">
            <ResultCard label="OOS Trades" value={result.oos_total_trades} />
            <ResultCard label="OOS Win Rate" value={`${(result.oos_win_rate * 100).toFixed(1)}%`} />
            <ResultCard label="OOS Sharpe" value={result.oos_sharpe.toFixed(2)}
              color={result.oos_sharpe > 0 ? "text-emerald-400" : "text-red-400"} />
            <ResultCard label="OOS PF" value={result.oos_profit_factor.toFixed(2)}
              color={result.oos_profit_factor > 1 ? "text-emerald-400" : "text-red-400"} />
            <ResultCard label="Max Drawdown" value={`$${result.oos_max_drawdown.toFixed(0)}`} color="text-red-400" />
            <ResultCard label="P-Value" value={result.p_value.toFixed(4)}
              icon={result.is_significant ? CheckCircle : XCircle}
              color={result.is_significant ? "text-emerald-400" : "text-amber-400"} />
          </div>

          <div className="grid grid-cols-4 gap-3">
            <ResultCard label="WF Windows" value={result.wf_num_windows} />
            <ResultCard label="Profitable Windows" value={`${(result.wf_pct_profitable_windows * 100).toFixed(0)}%`} />
            <ResultCard label="MC Ruin Prob" value={`${(result.mc_probability_of_ruin * 100).toFixed(1)}%`}
              color={result.mc_probability_of_ruin < 0.05 ? "text-emerald-400" : "text-red-400"} />
            <ResultCard label="Significant?" value={result.is_significant ? "YES" : "NO"}
              color={result.is_significant ? "text-emerald-400" : "text-red-400"} />
          </div>

          {equityData.length > 0 && (
            <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <h3 className="text-sm font-semibold text-gray-300 mb-3">Backtest Equity Curve</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={equityData}>
                  <XAxis dataKey="idx" tick={false} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#6b7280" }} />
                  <Tooltip contentStyle={{ backgroundColor: "#1a2332", border: "1px solid #243044", borderRadius: 8 }} />
                  <ReferenceLine y={50000} stroke="#374151" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="balance" stroke="#06b6d4" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultCard({ label, value, color = "text-gray-200", icon: Icon }: any) {
  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-800 text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color} flex items-center justify-center gap-1`}>
        {Icon && <Icon className="w-4 h-4" />}
        {value}
      </div>
    </div>
  );
}
