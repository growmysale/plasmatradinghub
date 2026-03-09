import React, { useState } from "react";
import CommandCenter from "./pages/CommandCenter";
import LiveChart from "./pages/LiveChart";
import AgentDeepDive from "./pages/AgentDeepDive";
import RiskDashboard from "./pages/RiskDashboard";
import BacktestCenter from "./pages/BacktestCenter";
import TradeJournal from "./pages/TradeJournal";
import Settings from "./pages/Settings";
import Sidebar from "./components/Sidebar";

type Page = "command" | "chart" | "agents" | "risk" | "backtest" | "journal" | "settings";

export default function App() {
  const [page, setPage] = useState<Page>("command");

  const pages: Record<Page, React.ReactNode> = {
    command: <CommandCenter />,
    chart: <LiveChart />,
    agents: <AgentDeepDive />,
    risk: <RiskDashboard />,
    backtest: <BacktestCenter />,
    journal: <TradeJournal />,
    settings: <Settings />,
  };

  return (
    <div className="flex h-screen bg-gray-950">
      <Sidebar activePage={page} onNavigate={(p) => setPage(p as Page)} />
      <main className="flex-1 overflow-auto p-4">{pages[page]}</main>
    </div>
  );
}
