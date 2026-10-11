"""
Phase 2: Alpha Diversification
Strategy: Statistical Arbitrage / Pairs Trading (Market Neutral)
Designed for: Generating alpha independent of market direction (zero beta).
"""

from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np


class StatisticalPairsStrategy:
    """
    Pairs Trading / Statistical Arbitrage between two cointegrated assets
    (e.g., KO & PEP, GOOGL & MSFT, or SPY & QQQ).
    
    Uses rolling Z-score of price spread ratio:
      Ratio = Price_A / Price_B
      Z-score = (Ratio - Rolling_Mean) / Rolling_Std
      
    Triggers:
      - Z > +2.0: Asset A is statistically overvalued vs Asset B -> SHORT A, LONG B
      - Z < -2.0: Asset A is statistically undervalued vs Asset B -> LONG A, SHORT B
      - |Z| < 0.5: Spread converged to mean -> EXIT ALL
    """

    def __init__(
        self,
        lookback_window: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        stop_z: float = 3.5,
    ):
        self.lookback_window = lookback_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z

    def compute_pair_zscore(self, df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.Series:
        """
        Aligns dates and calculates rolling Z-score of the price ratio.
        """
        close_a = df_a["close"]
        close_b = df_b["close"]

        # Align series on common dates
        combined = pd.DataFrame({"A": close_a, "B": close_b}).dropna()
        if len(combined) < self.lookback_window:
            return pd.Series(dtype=float)

        ratio = combined["A"] / combined["B"]
        rolling_mean = ratio.rolling(window=self.lookback_window).mean()
        rolling_std = ratio.rolling(window=self.lookback_window).std()

        zscore = (ratio - rolling_mean) / rolling_std.replace(0, np.nan)
        return zscore.dropna()

    def generate_pair_signals(
        self,
        symbol_a: str,
        df_a: pd.DataFrame,
        symbol_b: str,
        df_b: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Evaluates the pair relationship and generates market-neutral allocation signals.
        """
        zseries = self.compute_pair_zscore(df_a, df_b)
        if zseries.empty:
            return {
                "pair": f"{symbol_a}/{symbol_b}",
                "z_score": 0.0,
                "action": "INSUFFICIENT_DATA",
                "allocations": {symbol_a: 0.0, symbol_b: 0.0},
                "rationale": "Insufficient historical data to compute spread Z-score.",
            }

        curr_z = float(zseries.iloc[-1])

        # Overextended: Long B, Short A
        if curr_z >= self.entry_z and curr_z < self.stop_z:
            return {
                "pair": f"{symbol_a}/{symbol_b}",
                "z_score": round(curr_z, 2),
                "action": "ENTER_SPREAD_SHORT_A_LONG_B",
                "allocations": {symbol_a: -0.5, symbol_b: 0.5},
                "rationale": f"Z-Score={curr_z:.2f} > +{self.entry_z}. {symbol_a} overextended vs {symbol_b}. Short {symbol_a}, Long {symbol_b}.",
            }

        # Underextended: Long A, Short B
        elif curr_z <= -self.entry_z and curr_z > -self.stop_z:
            return {
                "pair": f"{symbol_a}/{symbol_b}",
                "z_score": round(curr_z, 2),
                "action": "ENTER_SPREAD_LONG_A_SHORT_B",
                "allocations": {symbol_a: 0.5, symbol_b: -0.5},
                "rationale": f"Z-Score={curr_z:.2f} < -{self.entry_z}. {symbol_a} undervalued vs {symbol_b}. Long {symbol_a}, Short {symbol_b}.",
            }

        # Convergence Exit
        elif abs(curr_z) <= self.exit_z:
            return {
                "pair": f"{symbol_a}/{symbol_b}",
                "z_score": round(curr_z, 2),
                "action": "EXIT_CONVERGED",
                "allocations": {symbol_a: 0.0, symbol_b: 0.0},
                "rationale": f"Z-Score={curr_z:.2f} returned within normal band (<= {self.exit_z}). Mean reversion complete. Liquidating pair.",
            }

        # Stop-loss threshold: spread blew out further than statistical normal
        elif abs(curr_z) >= self.stop_z:
            return {
                "pair": f"{symbol_a}/{symbol_b}",
                "z_score": round(curr_z, 2),
                "action": "STOP_LOSS_BREAKOUT",
                "allocations": {symbol_a: 0.0, symbol_b: 0.0},
                "rationale": f"Z-Score={curr_z:.2f} exceeded stop limit ({self.stop_z}). Cointegration breakdown risk. Cut position.",
            }

        return {
            "pair": f"{symbol_a}/{symbol_b}",
            "z_score": round(curr_z, 2),
            "action": "HOLD_NEUTRAL",
            "allocations": {symbol_a: 0.0, symbol_b: 0.0},
            "rationale": f"Z-Score={curr_z:.2f} inside neutral corridor.",
        }
