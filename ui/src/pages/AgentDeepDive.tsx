import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Users, ChevronRight, Cpu, Activity, Target, TrendingUp } from "lucide-react";

function AgentCard({ agent, isSelected, onClick }: any) {
  const weightPct = (agent.weight * 100).toFixed(0);
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-all ${
        isSelected
          ? "bg-cyan-500/10 border-cyan-500/30"
          : "bg-gray-900 border-gray-800 hover:border-gray-700"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-gray-200">{agent.agent_name}</span>
        <ChevronRight className={`w-4 h-4 transition-transform ${isSelected ? "rotate-90 text-cyan-400" : "text-gray-600"}`} />
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-cyan-500 rounded-full" style={{ width: `${weightPct}%` }} />
        </div>
        <span className="text-xs text-gray-500">{weightPct}%</span>
      </div>
      <div className="flex gap-2 mt-2">
        {agent.preferred_regimes?.map((r: string) => (
          <span key={r} className="text-[10px] px-1 py-0.5 rounded bg-gray-800 text-gray-500">
            {r.replace("_", " ")}
          </span>
        ))}
      </div>
    </button>
  );
}

export default function AgentDeepDive() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const { data: agentDetail } = useQuery({
    queryKey: ["agent-detail", selectedAgent],
    queryFn: () => selectedAgent ? api.getAgent(selectedAgent) : null,
    enabled: !!selectedAgent,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Users className="w-5 h-5 text-cyan-400" />
        <h1 className="text-xl font-bold">Agent Deep Dive</h1>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {/* Agent List */}
        <div className="space-y-2">
          {(agents || []).map((agent: any) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              isSelected={selectedAgent === agent.agent_id}
              onClick={() => setSelectedAgent(agent.agent_id)}
            />
          ))}
        </div>

        {/* Agent Detail */}
        <div className="col-span-3">
          {selectedAgent && agentDetail ? (
            <div className="space-y-4">
              <div className="bg-gray-900 rounded-lg p-5 border border-gray-800">
                <div className="flex items-center gap-3 mb-4">
                  <Cpu className="w-6 h-6 text-cyan-400" />
                  <div>
                    <h2 className="text-lg font-bold">{agentDetail.agent_name}</h2>
                    <p className="text-xs text-gray-500">ID: {agentDetail.agent_id} | Version: {agentDetail.version}</p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="bg-gray-800/50 rounded p-3">
                    <div className="text-xs text-gray-500 mb-1">Preferred Regimes</div>
                    <div className="flex flex-wrap gap-1">
                      {agentDetail.preferred_regimes?.map((r: string) => (
                        <span key={r} className="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400">
                          {r.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="bg-gray-800/50 rounded p-3">
                    <div className="text-xs text-gray-500 mb-1">Min Confidence</div>
                    <div className="text-lg font-bold text-gray-200">
                      {((agentDetail.min_confidence || 0.55) * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-gray-800/50 rounded p-3">
                    <div className="text-xs text-gray-500 mb-1">Status</div>
                    <div className="text-lg font-bold text-emerald-400">ACTIVE</div>
                  </div>
                </div>

                <h3 className="text-sm font-semibold text-gray-300 mb-2">Parameters</h3>
                <div className="bg-gray-950 rounded p-3 font-mono text-xs text-gray-400 max-h-60 overflow-auto">
                  {Object.entries(agentDetail.parameters || {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between py-1 border-b border-gray-800/50">
                      <span className="text-cyan-400">{k}</span>
                      <span className="text-gray-300">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-600">
              <div className="text-center">
                <Users className="w-12 h-12 mx-auto mb-2 opacity-30" />
                <p>Select an agent to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
