import pandas as pd
import numpy as np
from typing import Dict, List, Any
from trading_system.app.common.interfaces import PerformanceAnalyzer
from trading_system.app.common.logger import get_logger

logger = get_logger("PerformanceAnalyzer")

class QuantitativePerformanceAnalyzer(PerformanceAnalyzer):
    """
    Calculates institutional-grade risk and performance metrics (Sharpe, Drawdown, Calmar).
    """
    def __init__(self, risk_free_rate: float = 0.04):
        self.risk_free_rate = risk_free_rate
        
    def calculate_metrics(self, trade_history: List[Any], equity_curve: pd.Series) -> Dict[str, float]:
        if equity_curve.empty or len(equity_curve) < 2:
            return {}
            
        metrics = {}
        
        # Ensure index is datetime and sorted
        equity_curve = pd.Series(equity_curve).sort_index()
        
        # Calculate daily returns
        daily_returns = equity_curve.pct_change().dropna()
        
        if len(daily_returns) == 0:
            return {}
            
        # 1. Total Return
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        metrics["Total_Return_%"] = round(total_return * 100, 2)
        
        # 2. Annualized Return (Assuming 252 trading days)
        if isinstance(equity_curve.index, pd.DatetimeIndex):
            days = (equity_curve.index[-1] - equity_curve.index[0]).days
        elif hasattr(equity_curve.index[-1] - equity_curve.index[0], 'days'):
            days = (equity_curve.index[-1] - equity_curve.index[0]).days
        else:
            days = len(equity_curve) * (365.25 / 252.0)
            
        years = days / 365.25 if days > 0 else 0
        if years > 0 and total_return > -1.0:
            ann_return = (1.0 + total_return) ** (1.0 / years) - 1.0
        elif total_return <= -1.0:
            ann_return = -1.0
        else:
            ann_return = 0.0
        metrics["Annualized_Return_%"] = round(ann_return * 100, 2)
        
        # 3. Annualized Volatility
        daily_vol = daily_returns.std()
        ann_vol = daily_vol * np.sqrt(252)
        metrics["Annualized_Volatility_%"] = round(ann_vol * 100, 2)
        
        # 4. Sharpe Ratio
        if ann_vol > 0:
            sharpe = (ann_return - self.risk_free_rate) / ann_vol
        else:
            sharpe = 0.0
        metrics["Sharpe_Ratio"] = round(sharpe, 2)
        
        # 5. Maximum Drawdown
        rolling_max = equity_curve.cummax()
        drawdowns = (equity_curve - rolling_max) / rolling_max
        max_drawdown = drawdowns.min()
        metrics["Max_Drawdown_%"] = round(max_drawdown * 100, 2)
        
        # 6. Calmar Ratio
        if max_drawdown < 0:
            calmar = ann_return / abs(max_drawdown)
        else:
            calmar = np.nan
        metrics["Calmar_Ratio"] = round(calmar, 2)
        
        # 7. Daily Win Rate
        positive_days = len(daily_returns[daily_returns > 0])
        total_days = len(daily_returns)
        win_rate = positive_days / total_days if total_days > 0 else 0
        metrics["Daily_Win_Rate_%"] = round(win_rate * 100, 2)
        
        return metrics
