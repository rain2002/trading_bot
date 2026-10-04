import pandas as pd
from typing import Dict
from trading_system.app.common.logger import get_logger

logger = get_logger("CapacityAnalyzer")

class CapacityAnalysisModule:
    """
    Phase 17 Tool: Capacity / Scaling Tools.
    Models market impact and liquidity constraints to determine when a strategy
    will begin degrading due to excessive capital allocation.
    """
    
    def __init__(self, max_participation_rate=0.05, impact_coefficient=0.1):
        # We assume we cannot be more than 5% of the average daily volume without moving the market.
        self.max_participation_rate = max_participation_rate
        # A simple linear coefficient for market impact penalty estimation
        self.impact_coefficient = impact_coefficient
        
    def analyze_capital_capacity(self, target_portfolio_weights: Dict[str, float], 
                                 point_in_time_universe: Dict[str, pd.DataFrame], 
                                 proposed_capital: float) -> dict:
        """
        Evaluates a proposed capital increase against historical liquidity.
        """
        report = {
            "proposed_capital": proposed_capital,
            "is_capacity_safe": True,
            "limiting_assets": [],
            "estimated_impact_bps": 0.0,
            "asset_metrics": {}
        }
        
        total_impact_bps = 0.0
        active_assets = 0
        
        for sym, weight in target_portfolio_weights.items():
            if weight == 0 or weight == 'HOLD':
                continue
                
            if sym not in point_in_time_universe or point_in_time_universe[sym].empty:
                continue
                
            df = point_in_time_universe[sym]
            
            # Calculate 20-day Average Daily Volume (ADV) in Dollars
            # Volume is in shares, close is in dollars.
            recent_data = df.tail(20)
            avg_daily_volume_shares = recent_data['volume'].mean()
            current_price = recent_data['close'].iloc[-1]
            adv_dollars = avg_daily_volume_shares * current_price
            
            # Calculate our proposed trade size
            proposed_trade_dollars = proposed_capital * abs(weight)
            
            # Calculate participation rate
            participation_rate = proposed_trade_dollars / adv_dollars if adv_dollars > 0 else 1.0
            
            # Estimate slippage from market impact (Non-linear approximation: participation_rate ** 1.5)
            impact_bps = (participation_rate ** 1.5) * self.impact_coefficient * 10000
            
            total_impact_bps += impact_bps
            active_assets += 1
            
            is_safe = participation_rate <= self.max_participation_rate
            
            if not is_safe:
                report["is_capacity_safe"] = False
                report["limiting_assets"].append(sym)
                
            report["asset_metrics"][sym] = {
                "adv_dollars": adv_dollars,
                "proposed_trade_dollars": proposed_trade_dollars,
                "participation_rate": round(participation_rate, 4),
                "estimated_impact_bps": round(impact_bps, 2),
                "safe": is_safe
            }
            
        if active_assets > 0:
            report["estimated_impact_bps"] = round(total_impact_bps / active_assets, 2)
            
        return report

    def find_maximum_capacity(self, target_portfolio_weights: Dict[str, float], 
                              point_in_time_universe: Dict[str, pd.DataFrame]) -> float:
        """
        Reverse-engineers the mathematical maximum capital this strategy can handle
        before breaching the `max_participation_rate` on its most restrictive asset.
        """
        max_safe_capital = float('inf')
        
        for sym, weight in target_portfolio_weights.items():
            if weight == 0 or weight == 'HOLD' or sym not in point_in_time_universe:
                continue
                
            df = point_in_time_universe[sym]
            if df.empty: continue
            
            recent_data = df.tail(20)
            adv_dollars = recent_data['volume'].mean() * recent_data['close'].iloc[-1]
            
            # max_trade_dollars = adv_dollars * self.max_participation_rate
            # max_capital = max_trade_dollars / abs(weight)
            if abs(weight) > 0:
                asset_max_capital = (adv_dollars * self.max_participation_rate) / abs(weight)
                if asset_max_capital < max_safe_capital:
                    max_safe_capital = asset_max_capital
                    
        return max_safe_capital if max_safe_capital != float('inf') else 0.0
