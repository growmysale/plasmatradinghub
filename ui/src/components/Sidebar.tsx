import React from "react";
import {
  LayoutDashboard, LineChart, Users, Shield, FlaskConical,
  BookOpen, Settings as SettingsIcon, Brain,
} from "lucide-react";

interface Props {
  activePage: string;
  onNavigate: (page: string) => void;
}

const NAV_ITEMS = [
  { id: "command", label: "Command Center", icon: LayoutDashboard },
  { id: "chart", label: "Live Chart", icon: LineChart },
  { id: "agents", label: "Agent Deep Dive", icon: Users },
  { id: "risk", label: "Risk Dashboard", icon: Shield },
  { id: "backtest", label: "Backtest Center", icon: FlaskConical },
  { id: "journal", label: "Trade Journal", icon: BookOpen },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export default function Sidebar({ activePage, onNavigate }: Props) {
  return (
    <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <Brain className="w-6 h-6 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-cyan-400">PropEdge v2</h1>
            <p className="text-[10px] text-gray-500">Neural Trading System</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 py-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-cyan-500/10 text-cyan-400 border-r-2 border-cyan-400"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="p-3 border-t border-gray-800">
        <div className="text-[10px] text-gray-600 text-center">
          Adaptive Neural Trading System
        </div>
      </div>
    </aside>
  );
}
