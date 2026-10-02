from datetime import datetime
from typing import Dict, List
import pandas as pd
from sqlalchemy.orm import Session
from trading_system.app.common.logger import get_logger
from trading_system.app.models.core import Experiment, Order
import uuid
import json

logger = get_logger("MultiAssetBacktester")

class MultiAssetBacktester:
    """
    Advanced backtesting engine handling an entire universe of stocks simultaneously, 
    maintaining strict point-in-time constraints across all assets.
    """
    def __init__(self, data_provider, strategy, portfolio, risk_engine, portfolio_constructor, execution_adapter, db_session: Session):
        self.data_provider = data_provider
        self.strategy = strategy
        self.portfolio = portfolio
        self.risk_engine = risk_engine
        self.portfolio_constructor = portfolio_constructor
        self.execution_adapter = execution_adapter
        self.db = db_session
        
    def run(self, symbols: List[str], start_date: datetime, end_date: datetime, experiment_id: str = None):
        if not experiment_id:
            experiment_id = f"EXP-{uuid.uuid4().hex[:8]}"
            
        logger.info(f"Starting Multi-Asset Backtest: {experiment_id} for {len(symbols)} symbols")
        
        # 1. Fetch data for all symbols in the universe
        universe_data = {}
        all_dates = set()
        for sym in symbols:
            df = self.data_provider.fetch_historical_data(sym, start_date, end_date)
            if not df.empty:
                universe_data[sym] = df
                all_dates.update(df.index.tolist())
                
        if not universe_data:
            logger.error("No data fetched for any symbols.")
            return None
            
        # Sort the global market timeline
        timeline = sorted(list(all_dates))
        
        # 2. Event loop stepping through the global timeline
        for t_idx in range(len(timeline)):
            current_time = timeline[t_idx]
            
            # Build strictly point-in-time data dictionary for the entire universe
            point_in_time_universe = {}
            for sym, df in universe_data.items():
                pit_df = df[df.index <= current_time]
                if not pit_df.empty:
                    point_in_time_universe[sym] = pit_df.copy()
            
            # 3. Strategy evaluates the entire universe and generates cross-sectional signals
            signals = self.strategy.generate_signals(point_in_time_universe)
            
            # 4. Portfolio Construction (Signals -> Target Portfolio Weights)
            target_weights = self.portfolio_constructor.generate_target_weights(signals)
            
            # 5. Order Generation (Compare target weights to current portfolio state)
            total_equity = self.portfolio.cash
            current_positions = self.portfolio.get_positions()
            
            # Estimate total dynamic equity including open positions (Mark-to-Market)
            for sym, qty in current_positions.items():
                if sym in point_in_time_universe and not point_in_time_universe[sym].empty:
                    last_price = point_in_time_universe[sym]['close'].iloc[-1]
                    total_equity += (qty * last_price)
            
            # Generate required trades to reach the new target weights
            for sym, target_weight in target_weights.items():
                target_value = total_equity * target_weight
                
                if sym not in point_in_time_universe or point_in_time_universe[sym].empty:
                    continue
                current_price = point_in_time_universe[sym]['close'].iloc[-1]
                
                current_qty = current_positions.get(sym, 0.0)
                current_value = current_qty * current_price
                
                value_to_trade = target_value - current_value
                qty_to_trade = int(value_to_trade / current_price)
                
                if qty_to_trade != 0:
                    trade_request = {
                        "client_order_id": str(uuid.uuid4()),
                        "symbol": sym,
                        "quantity": qty_to_trade,
                        "price_hint": current_price
                    }
                    
                    # 6. Global Risk Check (e.g., Prop Firm Drawdown limits)
                    if self.risk_engine.evaluate_trade(trade_request, current_positions):
                        # 7. Execute with slippage
                        fill = self.execution_adapter.submit_order(trade_request)
                        if fill['status'] == 'FILLED':
                            self.portfolio.update_position(sym, fill['filled_quantity'], fill['fill_price'])
                            
                            db_order = Order(
                                client_order_id=fill['order_id'],
                                symbol=sym,
                                quantity=fill['filled_quantity'],
                                price=fill['fill_price'],
                                status=fill['status'],
                                filled_at=datetime.utcnow()
                            )
                            self.db.add(db_order)
                            
        # Commit experiment metrics
        exp = Experiment(
            experiment_id=experiment_id,
            strategy_id=self.strategy.__class__.__name__,
            dataset_version="multi-asset-batch",
            parameters=json.dumps({"symbols": symbols}),
            metrics=json.dumps({"final_equity": total_equity})
        )
        self.db.add(exp)
        self.db.commit()
        
        logger.info(f"Multi-Asset Backtest {experiment_id} Complete")
        return self.portfolio
