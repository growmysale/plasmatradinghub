"""Genetic Strategy Evolution.

Continuously breeds, tests, and selects strategy parameter variants.
The system gets BETTER over time via Darwinian selection.

Evolution Loop:
  1. MUTATION: Randomly adjust 1-3 parameters within +/-20%
  2. CROSSOVER: Combine params from two profitable agents
  3. EVALUATION: Walk-forward backtest each variant
  4. SELECTION: Top 10% survive, bottom 90% killed
  5. PROMOTION: Paper-traded variants that outperform get promoted
  6. EXTINCTION: Agents with rolling OOS Sharpe < 0 get killed
"""
from __future__ import annotations

import copy
import logging
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agents.base import StrategyAgent
from agents.registry import get_agent, AGENT_CLASSES
from backtester.engine import BacktestEngine, BacktestResult
from core.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class Individual:
    """A strategy variant in the evolution population."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_type: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    parent_ids: List[str] = field(default_factory=list)
    generation: int = 0
    fitness: float = 0.0
    oos_sharpe: float = 0.0
    oos_profit_factor: float = 0.0
    oos_max_drawdown: float = 0.0
    survived: bool = False
    promoted: bool = False


class EvolutionEngine:
    """Genetic strategy optimization engine."""

    def __init__(self):
        self.config = get_config().evolution
        self.backtester = BacktestEngine()
        self._population: List[Individual] = []
        self._generation = 0
        self._history: List[List[Individual]] = []

    def initialize_population(self, agent_types: Optional[List[str]] = None):
        """Create initial population from existing agent parameters."""
        agent_types = agent_types or list(AGENT_CLASSES.keys())

        for agent_type in agent_types:
            agent = get_agent(agent_type)
            if not agent:
                continue

            base_params = agent.get_parameters()

            # Create variants with random mutations
            for i in range(self.config.population_size // len(agent_types)):
                params = self._mutate(base_params)
                self._population.append(Individual(
                    agent_type=agent_type,
                    params=params,
                    generation=0,
                ))

        logger.info(f"Initialized population: {len(self._population)} individuals")

    def _mutate(self, params: Dict[str, Any], mutation_range: Optional[float] = None) -> Dict[str, Any]:
        """Randomly adjust 1-3 numeric parameters."""
        mutation_range = mutation_range or self.config.mutation_range
        mutated = copy.deepcopy(params)

        numeric_keys = [k for k, v in mutated.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not numeric_keys:
            return mutated

        n_mutations = random.randint(1, min(3, len(numeric_keys)))
        keys_to_mutate = random.sample(numeric_keys, n_mutations)

        for key in keys_to_mutate:
            val = mutated[key]
            delta = val * random.uniform(-mutation_range, mutation_range)
            if isinstance(val, int):
                mutated[key] = max(1, int(val + delta))
            else:
                mutated[key] = round(val + delta, 6)

        return mutated

    def _crossover(self, parent1: Individual, parent2: Individual) -> Individual:
        """Combine parameters from two parents."""
        if parent1.agent_type != parent2.agent_type:
            return copy.deepcopy(parent1)

        child_params = {}
        for key in parent1.params:
            if key in parent2.params:
                # 50/50 chance of taking from either parent
                if random.random() < 0.5:
                    child_params[key] = parent1.params[key]
                else:
                    child_params[key] = parent2.params[key]
            else:
                child_params[key] = parent1.params[key]

        return Individual(
            agent_type=parent1.agent_type,
            params=child_params,
            parent_ids=[parent1.id, parent2.id],
            generation=self._generation + 1,
        )

    def evaluate_individual(self, individual: Individual, candles: pd.DataFrame) -> float:
        """Run walk-forward backtest on an individual and compute fitness."""
        agent = get_agent(individual.agent_type)
        if not agent:
            return -999

        agent.set_parameters(individual.params)

        try:
            result = self.backtester.walk_forward(agent, candles, train_days=30, test_days=5)
        except Exception as e:
            logger.error(f"Evaluation failed for {individual.id}: {e}")
            return -999

        individual.oos_sharpe = result.oos_sharpe
        individual.oos_profit_factor = result.oos_profit_factor
        individual.oos_max_drawdown = result.oos_max_drawdown

        # Fitness = (OOS Sharpe * OOS Profit Factor) / max_drawdown
        dd = max(individual.oos_max_drawdown, 1.0)
        fitness = (individual.oos_sharpe * max(individual.oos_profit_factor, 0.01)) / dd

        individual.fitness = round(fitness, 6)
        return fitness

    def evolve_generation(self, candles: pd.DataFrame) -> List[Individual]:
        """Run one generation of evolution."""
        self._generation += 1
        logger.info(f"Generation {self._generation}: evaluating {len(self._population)} individuals")

        # Evaluate all individuals
        for ind in self._population:
            self.evaluate_individual(ind, candles)

        # Sort by fitness (descending)
        self._population.sort(key=lambda x: x.fitness, reverse=True)

        # Selection: top N% survive
        n_survivors = max(2, int(len(self._population) * self.config.survival_rate))
        survivors = self._population[:n_survivors]
        for s in survivors:
            s.survived = True

        logger.info(f"Generation {self._generation}: {n_survivors} survivors, "
                    f"best fitness={survivors[0].fitness:.4f}")

        # Generate new population
        new_pop = list(survivors)

        target_size = self.config.population_size
        while len(new_pop) < target_size:
            if random.random() < self.config.crossover_rate and len(survivors) >= 2:
                # Crossover
                p1, p2 = random.sample(survivors, 2)
                child = self._crossover(p1, p2)
                child.params = self._mutate(child.params)
                new_pop.append(child)
            else:
                # Mutation of random survivor
                parent = random.choice(survivors)
                child = Individual(
                    agent_type=parent.agent_type,
                    params=self._mutate(parent.params),
                    parent_ids=[parent.id],
                    generation=self._generation,
                )
                new_pop.append(child)

        self._population = new_pop
        self._history.append(survivors)

        return survivors

    def get_best_individuals(self, n: int = 5) -> List[Individual]:
        """Get the top N individuals from current population."""
        sorted_pop = sorted(self._population, key=lambda x: x.fitness, reverse=True)
        return sorted_pop[:n]

    def get_generation_stats(self) -> Dict[str, Any]:
        """Get stats for the current generation."""
        fitnesses = [ind.fitness for ind in self._population]
        return {
            "generation": self._generation,
            "population_size": len(self._population),
            "best_fitness": max(fitnesses) if fitnesses else 0,
            "avg_fitness": np.mean(fitnesses) if fitnesses else 0,
            "worst_fitness": min(fitnesses) if fitnesses else 0,
        }
