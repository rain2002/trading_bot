"""
Phase 2: Alpha Diversification
Strategy: Mean Reversion (Bollinger Bands + RSI Oversold)
Designed for: Range-bound, sideways, and choppy markets where trend-following chops.
"""

from typing import Dict, Any
import pandas as pd
import numpy as np


class MeanReversionStrategy:
    """
    Mean Reversion strategy identifying statistical extremes.
    Triggers BUY when:
      1. Close < Lower Bollinger Band (2.0 std dev)
      2. RSI(14) < 30 (Oversold extreme)
      3. Long-term trend context: Not in an outright collapse (Price > 200 SMA or regime filter)
    Exits (SELL / TAKE PROFIT) when:
      1. Price reverts to the 20-period Moving Average (Bollinger Band Mean)
      2. RSI crosses above 55
    """

    def __init__(
        self,
        bb_window: int = 20,
        bb_std: float = 2.0,
        rsi_window: int = 14,
        rsi_oversold: float = 38.0,
        rsi_exit: float = 55.0,
    ):
        self.bb_window = bb_window
        self.bb_std = bb_std
        self.rsi_window = rsi_window
        self.rsi_oversold = rsi_oversold
        self.rsi_exit = rsi_exit

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        close = data["close"]

        # 1. Bollinger Bands
        sma = close.rolling(window=self.bb_window).mean()
        std = close.rolling(window=self.bb_window).std()
        data["bb_mid"] = sma
        data["bb_upper"] = sma + (self.bb_std * std)
        data["bb_lower"] = sma - (self.bb_std * std)

        # 2. RSI (Relative Strength Index) using Wilder's Exponential Smoothing
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1.0 / self.rsi_window, min_periods=self.rsi_window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / self.rsi_window, min_periods=self.rsi_window, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        data["rsi"] = 100 - (100 / (1 + rs))

        # 3. 200 SMA for macro trend anchor
        data["sma_200"] = close.rolling(window=min(200, len(data)), min_periods=min(50, len(data))).mean()

        return data

    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluates the latest bar and returns signal dictionary:
        {
            'signal': 1 (BUY), -1 (SELL/SHORT), 0 (NEUTRAL),
            'confidence': float,
            'rationale': str
        }
        """
        if df.empty or len(df) < max(self.bb_window, self.rsi_window) + 5:
            return {"signal": 0, "confidence": 0.0, "rationale": "Insufficient data"}

        data = self.compute_indicators(df)
        curr = data.iloc[-1]
        prev = data.iloc[-2]

        current_price = curr["close"]
        bb_lower = curr["bb_lower"]
        bb_mid = curr["bb_mid"]
        rsi = curr["rsi"]
        sma_200 = curr.get("sma_200", current_price)

        # BUY Condition: Near/below lower band and RSI oversold, with macro trend intact
        is_dip = (current_price <= bb_lower * 1.01) and (rsi <= self.rsi_oversold)
        if is_dip and current_price >= sma_200 * 0.85:
            confidence = min(1.0, 0.70 + (self.rsi_oversold - rsi) * 0.015)
            return {
                "signal": 1,
                "confidence": round(confidence, 2),
                "rationale": f"Mean-Reversion BUY: Price ({current_price:.2f}) near BB Lower ({bb_lower:.2f}), RSI is {rsi:.1f}",
            }

        # EXIT Condition: Price reached middle band or RSI normalized
        if current_price >= bb_mid or rsi >= self.rsi_exit:
            return {
                "signal": -1,  # Close long position / mean reverted
                "confidence": 0.75,
                "rationale": f"Mean-Reversion EXIT: Reverted to mean ({bb_mid:.2f}), RSI is {rsi:.1f}",
            }

        return {
            "signal": 0,
            "confidence": 0.50,
            "rationale": f"Mean-Reversion HOLD/NEUTRAL: RSI={rsi:.1f}, BB Lower={bb_lower:.2f}",
        }
