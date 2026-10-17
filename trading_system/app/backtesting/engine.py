from datetime import datetime
from typing import Dict, Any
import pandas as pd
from sqlalchemy.orm import Session
from trading_system.app.common.logger import get_logger
from trading_system.app.models.core import Experiment, Order
import uuid
import json

logger = get_logger("EventDrivenBacktester")

class EventDrivenBacktester:
    """
    Production-grade event-driven backtesting engine ensuring strict point-in-time logic.
    Pipelines data through: Strategy -> Risk -> PositionSizer -> Execution -> Portfolio -> Database.
    """
    def __init__(self, data_provider, strategy, portfolio, risk_engine, position_sizer, execution_adapter, db_session: Session):
        self.data_provider = data_provider
        self.strategy = strategy
        self.portfolio = portfolio
        self.risk_engine = risk_engine
        self.position_sizer = position_sizer
        self.execution_adapter = execution_adapter
        self.db = db_session
        
    def run(self, symbol: str, start_date: datetime, end_date: datetime, experiment_id: str = None):
        if not experiment_id:
            experiment_id = f"EXP-{uuid.uuid4().hex[:8]}"
            
        logger.info(f"Starting Backtest Experiment: {experiment_id} for {symbol}")
        
        # 1. Fetch full point-in-time data
        full_data = self.data_provider.fetch_historical_data(symbol, start_date, end_date)
        if full_data.empty:
            logger.error("No data returned for backtest.")
            return None
            
        dataset_version = full_data.attrs.get('lineage', {}).get('version_hash', 'unknown')
        
        # 2. Event loop (Simulating strict point-in-time constraints)
        for i in range(len(full_data)):
            # Create the point-in-time slice strictly up to index 'i'
            # STRICT LEAKAGE PREVENTION: Never expose i+1 or beyond
            current_time = full_data.index[i]
            point_in_time_data = full_data.iloc[:i+1].copy() # Copy to prevent accidental mutation
            
            # 3. Strategy Signal Generation
            signal_obj = self.strategy.generate_signal(point_in_time_data)
            signal = signal_obj.get("signal", 0)
            
            if signal != 0:
                current_price = point_in_time_data['close'].iloc[-1]
                
                # 4. Position Sizing
                trade_qty = self.position_sizer.calculate_size(
                    signal=signal, 
                    risk_parameters=None, 
                    capital=self.portfolio.cash
                )
                
                trade_request = {
                    "client_order_id": str(uuid.uuid4()),
                    "symbol": symbol,
                    "quantity": trade_qty,
                    "price_hint": current_price
                }
                
                # 5. Independent Risk Engine Evaluation
                if self.risk_engine.evaluate_trade(trade_request, self.portfolio.get_positions()):
                    
                    # 6. Order Execution Simulator (Applies Slippage & Fees)
                    fill = self.execution_adapter.submit_order(trade_request)
                    
                    # 7. Portfolio Update & Database Logging
                    if fill['status'] == 'FILLED':
                        self.portfolio.update_position(symbol, fill['filled_quantity'], fill['fill_price'])
                        
                        # Log to DB
                        side = "buy" if fill['filled_quantity'] > 0 else "sell"
                        db_order = Order(
                            client_order_id=fill['order_id'],
                            symbol=symbol,
                            quantity=abs(fill['filled_quantity']),
                            side=side,
                            price=fill['fill_price'],
                            status=fill['status']
                        )
                        self.db.add(db_order)
                        
                        logger.info(
                            f"Trade Executed: {symbol}",
                            extra={
                                "symbol": symbol,
                                "signal": signal,
                                "fill_price": fill['fill_price'],
                                "order_id": fill['order_id']
                            }
                        )
                else:
                    logger.warning(f"Trade rejected by Risk Engine for {symbol}", extra={"signal": signal, "attempted_qty": trade_qty})
                    
        # Log Experiment to DB to guarantee reproducibility
        exp = Experiment(
            experiment_id=experiment_id,
            strategy_id=self.strategy.__class__.__name__,
            dataset_version=dataset_version,
            parameters={"symbol": symbol},
            metrics={"final_cash": self.portfolio.cash}
        )
        self.db.add(exp)
        self.db.commit()
        
        logger.info(f"Backtest {experiment_id} Complete")
        return self.portfolio
