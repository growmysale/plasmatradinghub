"""Agent Registry - Manages all available strategy agents."""
from __future__ import annotations

from typing import Dict, List, Optional

from agents.base import StrategyAgent
from agents.smc_break_retest import SMCBreakRetestAgent
from agents.vwap_mean_reversion import VWAPMeanReversionAgent
from agents.orb_breakout import ORBBreakoutAgent
from agents.order_block_fvg import OBFVGAgent
from agents.momentum import MomentumAgent


# All available agent classes
AGENT_CLASSES = {
    "smc_br": SMCBreakRetestAgent,
    "vwap_mr": VWAPMeanReversionAgent,
    "orb": ORBBreakoutAgent,
    "ob_fvg": OBFVGAgent,
    "momentum": MomentumAgent,
}


def get_all_agents() -> List[StrategyAgent]:
    """Create instances of all registered agents."""
    return [cls() for cls in AGENT_CLASSES.values()]


def get_agent(agent_id: str) -> Optional[StrategyAgent]:
    """Get a specific agent by ID."""
    cls = AGENT_CLASSES.get(agent_id)
    if cls:
        return cls()
    return None


def register_agent(agent_id: str, agent_class: type):
    """Register a new agent class."""
    AGENT_CLASSES[agent_id] = agent_class
