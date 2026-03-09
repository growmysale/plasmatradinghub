import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { BookOpen, TrendingUp, TrendingDown } from "lucide-react";

export default function TradeJournal() {
  const { data: trades } = useQuery({ queryKey: ["trades"], queryFn: () => api.getTrades(100) });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-cyan-400" />
        <h1 className="text-xl font-bold">Trade Journal</h1>
      </div>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400">
              <th className="text-left p-3">Time</th>
              <th className="text-left p-3">Direction</th>
              <th className="text-right p-3">Entry</th>
              <th className="text-right p-3">Exit</th>
              <th className="text-right p-3">P&L</th>
              <th className="text-left p-3">Agents</th>
              <th className="text-left p-3">Regime</th>
              <th className="text-left p-3">Mode</th>
            </tr>
          </thead>
          <tbody>
            {(trades || []).map((trade: any) => {
              const pnlColor = (trade.pnl || 0) >= 0 ? "text-emerald-400" : "text-red-400";
              const DirIcon = trade.direction === "LONG" ? TrendingUp : TrendingDown;
              return (
                <tr key={trade.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="p-3 text-xs text-gray-400">{trade.ts_open?.substring(0, 16)}</td>
                  <td className="p-3">
                    <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded ${
                      trade.direction === "LONG" ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
                    }`}>
                      <DirIcon className="w-3 h-3" />
                      {trade.direction}
                    </span>
                  </td>
                  <td className="p-3 text-right font-mono text-gray-300">{trade.entry_price?.toFixed(2)}</td>
                  <td className="p-3 text-right font-mono text-gray-300">{trade.exit_price?.toFixed(2) || "-"}</td>
                  <td className={`p-3 text-right font-mono font-bold ${pnlColor}`}>
                    {trade.pnl != null ? `$${trade.pnl.toFixed(2)}` : "-"}
                  </td>
                  <td className="p-3 text-xs text-gray-500">{trade.agent_signals?.join(", ") || "-"}</td>
                  <td className="p-3 text-xs text-gray-500">{trade.regime?.replace("_", " ") || "-"}</td>
                  <td className="p-3">
                    <span className={`text-[10px] px-1 py-0.5 rounded ${
                      trade.mode === "live" ? "bg-red-500/20 text-red-400" :
                      trade.mode === "paper" ? "bg-amber-500/20 text-amber-400" :
                      "bg-gray-700 text-gray-400"
                    }`}>
                      {trade.mode?.toUpperCase()}
                    </span>
                  </td>
                </tr>
              );
            })}
            {(!trades || trades.length === 0) && (
              <tr>
                <td colSpan={8} className="p-8 text-center text-gray-600">No trades yet. Run a backtest or start sandbox mode.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
