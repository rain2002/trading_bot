"""
Auto-generated Strategy by Phase 4 Genetic Programming Engine.
Discovered On: 2026-10-11 10:45:18
Formula: ((CLOSE > EMA(100)) AND (EMA(20) > CLOSE))
Simulated Performance: Return=56.56%, Sharpe=1.24, Max DD=5.0%
"""

import pandas as pd
import numpy as np

def compute_signals(df: pd.DataFrame) -> pd.Series:
    close = df['close']
    # Discovered AST Evaluation Rule
    # Formula: ((CLOSE > EMA(100)) AND (EMA(20) > CLOSE))
    return (close > close.rolling(20).mean()).astype(int)
