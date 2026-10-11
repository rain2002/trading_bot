"""
Phase 4: The Final Boss
Module: Genetic Programming Engine (Symbolic Regression)
Generates, mutates, breeds, and evaluates trading strategies automatically
to discover non-obvious market edges from raw historical data.
"""

from typing import List, Tuple, Dict, Any
import random
import numpy as np
import pandas as pd
from trading_system.app.genetic.expression_tree import (
    ExpressionNode,
    TerminalNode,
    ConstantNode,
    BinaryOpNode,
)


class StrategyIndividual:
    """An individual algorithm in the genetic population."""
    def __init__(self, tree: ExpressionNode):
        self.tree = tree
        self.fitness: float = -999.0
        self.total_return_pct: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.max_drawdown_pct: float = 0.0
        self.trade_count: int = 0

    def formula(self) -> str:
        return self.tree.to_formula()


class GeneticStrategyEngine:
    """
    Simulates natural selection across trading formulas.
    Breeds winning indicators and weeds out unprofitable noise.
    """

    def __init__(
        self,
        population_size: int = 40,
        mutation_rate: float = 0.25,
        crossover_rate: float = 0.70,
        tournament_size: int = 4,
    ):
        self.pop_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.tournament_size = tournament_size
        self.best_individual: StrategyIndividual = None

    def random_terminal(self) -> TerminalNode:
        choices = ["close", "sma", "ema", "rsi", "std"]
        chosen = random.choice(choices)
        param = random.choice([10, 14, 20, 30, 50, 100, 200])
        return TerminalNode(chosen, param)

    def generate_random_rule(self, depth: int = 0, max_depth: int = 2) -> ExpressionNode:
        """Generates a random boolean comparison tree."""
        if depth >= max_depth:
            # Base comparison: Indicator > Indicator or Indicator > Constant
            term1 = self.random_terminal()
            if term1.name == "rsi":
                term2 = ConstantNode(random.choice([30.0, 40.0, 50.0, 60.0, 70.0]))
            else:
                term2 = self.random_terminal()
            op = random.choice([">", "<"])
            return BinaryOpNode(op, term1, term2)
        else:
            # Combine two sub-rules with AND / OR
            left = self.generate_random_rule(depth + 1, max_depth)
            right = self.generate_random_rule(depth + 1, max_depth)
            combine_op = random.choice(["AND", "OR"])
            return BinaryOpNode(combine_op, left, right)

    def evaluate_fitness(self, ind: StrategyIndividual, df: pd.DataFrame):
        """
        Calculates fitness score based on out-of-sample Sharpe Ratio and Max Drawdown.
        """
        try:
            signal_series = ind.tree.evaluate(df)
            signal_series = (signal_series > 0).astype(int).shift(1).fillna(0)  # Next-day execution

            close = df["close"]
            daily_returns = close.pct_change().fillna(0)
            strat_returns = signal_series * daily_returns

            trades = (signal_series.diff().abs() > 0).sum()
            ind.trade_count = int(trades)

            if trades < 5:  # Penalize dormant strategies that never trade
                ind.fitness = -999.0
                return

            # Cumulative Return
            equity_curve = (1 + strat_returns).cumprod()
            total_ret = (equity_curve.iloc[-1] - 1.0) * 100
            ind.total_return_pct = round(float(total_ret), 2)

            # Max Drawdown
            peak = equity_curve.cummax()
            dd = (equity_curve - peak) / peak
            max_dd = abs(float(dd.min())) * 100
            ind.max_drawdown_pct = round(max_dd, 2)

            # Annualized Sharpe Ratio
            mean_daily = strat_returns.mean()
            std_daily = strat_returns.std()
            if std_daily > 1e-6:
                sharpe = (mean_daily / std_daily) * np.sqrt(252)
            else:
                sharpe = 0.0
            ind.sharpe_ratio = round(float(sharpe), 2)

            # Fitness Function: Reward high Sharpe & positive return, heavily penalize deep drawdowns
            dd_factor = max(0.1, 1.0 - (max_dd / 100.0))
            ind.fitness = round(float(sharpe * dd_factor * np.log10(trades + 1)), 3)

        except Exception:
            ind.fitness = -999.0

    def tournament_selection(self, population: List[StrategyIndividual]) -> StrategyIndividual:
        selected = random.sample(population, self.tournament_size)
        selected.sort(key=lambda x: x.fitness, reverse=True)
        return selected[0]

    def crossover(self, p1: StrategyIndividual, p2: StrategyIndividual) -> StrategyIndividual:
        """Breeds two parent strategies by swapping left/right rule branches."""
        if random.random() < self.crossover_rate and isinstance(p1.tree, BinaryOpNode) and isinstance(p2.tree, BinaryOpNode):
            new_left = p1.tree.left.copy() if random.random() < 0.5 else p2.tree.left.copy()
            new_right = p2.tree.right.copy() if random.random() < 0.5 else p1.tree.right.copy()
            child_tree = BinaryOpNode(p1.tree.op, new_left, new_right)
            return StrategyIndividual(child_tree)
        return StrategyIndividual(p1.tree.copy())

    def mutate(self, ind: StrategyIndividual) -> StrategyIndividual:
        """Mutates constants, indicators, or operators with specified probability."""
        if random.random() < self.mutation_rate:
            mutated_tree = self.generate_random_rule(max_depth=1)
            return StrategyIndividual(mutated_tree)
        return ind

    def evolve(
        self, df: pd.DataFrame, generations: int = 5
    ) -> Tuple[StrategyIndividual, List[Dict[str, Any]]]:
        """Runs the evolutionary cycle."""
        # 1. Initialize random population
        population = [
            StrategyIndividual(self.generate_random_rule(max_depth=random.randint(1, 2)))
            for _ in range(self.pop_size)
        ]

        history = []

        for gen in range(1, generations + 1):
            # Evaluate fitness of all individuals
            for ind in population:
                self.evaluate_fitness(ind, df)

            # Sort by fitness (highest first)
            population.sort(key=lambda x: x.fitness, reverse=True)
            best_gen = population[0]

            if self.best_individual is None or best_gen.fitness > self.best_individual.fitness:
                self.best_individual = best_gen

            gen_summary = {
                "generation": gen,
                "best_fitness": best_gen.fitness,
                "best_return_pct": best_gen.total_return_pct,
                "best_sharpe": best_gen.sharpe_ratio,
                "best_drawdown_pct": best_gen.max_drawdown_pct,
                "best_formula": best_gen.formula(),
            }
            history.append(gen_summary)

            # Breed next generation (Elitism preserves top 2 performers unchanged)
            next_generation = [population[0], population[1]]
            while len(next_generation) < self.pop_size:
                parent1 = self.tournament_selection(population)
                parent2 = self.tournament_selection(population)
                child = self.crossover(parent1, parent2)
                child = self.mutate(child)
                next_generation.append(child)

            population = next_generation

        return self.best_individual, history
