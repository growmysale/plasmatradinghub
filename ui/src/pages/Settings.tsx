import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Settings as SettingsIcon, Database, Shield, Cpu, Zap } from "lucide-react";

function ConfigSection({ title, icon: Icon, children }: any) {
  return (
    <div className="bg-gray-900 rounded-lg p-5 border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
        <Icon className="w-4 h-4 text-cyan-400" />
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-gray-800/50">
      <span className="text-sm text-gray-400">{label}</span>
      <span className="text-sm font-mono text-gray-200">{String(value)}</span>
    </div>
  );
}

export default function Settings() {
  const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.getHealth });

  const c = config || { prop_firm: {}, personal_risk: {}, execution: {}, allocator: {} };
  const h = health || {};

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <SettingsIcon className="w-5 h-5 text-cyan-400" />
        <h1 className="text-xl font-bold">System Configuration</h1>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <ConfigSection title="System Health" icon={Zap}>
          <ConfigRow label="Status" value={h.status || "unknown"} />
          <ConfigRow label="Version" value={h.version || "2.0.0"} />
          <ConfigRow label="Mode" value={h.mode || "sandbox"} />
          <ConfigRow label="Candles Loaded" value={h.candles_loaded || 0} />
          <ConfigRow label="Agents Available" value={h.agents_available || 0} />
          <ConfigRow label="Features Count" value={h.features_count || 0} />
        </ConfigSection>

        <ConfigSection title="Prop Firm Rules" icon={Shield}>
          <ConfigRow label="Account" value={c.prop_firm?.name || "TopstepX $50K"} />
          <ConfigRow label="Initial Balance" value={`$${c.prop_firm?.initial_balance || 50000}`} />
          <ConfigRow label="Max Loss Limit" value={`$${c.prop_firm?.max_loss_limit || 2000}`} />
          <ConfigRow label="Profit Target" value={`$${c.prop_firm?.profit_target || 3000}`} />
        </ConfigSection>

        <ConfigSection title="Personal Risk Rules" icon={Shield}>
          <ConfigRow label="PDLL" value={`$${c.personal_risk?.pdll || 200}`} />
          <ConfigRow label="PDPT" value={`$${c.personal_risk?.pdpt || 300}`} />
          <ConfigRow label="Max Trades/Day" value={c.personal_risk?.max_trades || 3} />
          <ConfigRow label="Max Risk/Trade" value={`$${c.personal_risk?.max_risk_per_trade || 50}`} />
          <ConfigRow label="Min R:R" value={`${c.personal_risk?.min_rr || 2.0}:1`} />
        </ConfigSection>

        <ConfigSection title="Allocator" icon={Cpu}>
          <ConfigRow label="Method" value={c.allocator?.method || "weighted_vote"} />
          <ConfigRow label="Min Confidence" value={`${((c.allocator?.min_confidence || 0.6) * 100).toFixed(0)}%`} />
          <ConfigRow label="Execution Mode" value={c.execution?.mode || "sandbox"} />
        </ConfigSection>
      </div>
    </div>
  );
}
