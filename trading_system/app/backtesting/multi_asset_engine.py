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
    def __init__(self, data_provider, strategy, portfolio, risk_engine, portfolio_constructor, execution_adapter, db_session: Session = None):
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
                    
            # Check for Corporate Actions (Splits/Dividends) that occurred TODAY and apply them to the portfolio
            today_splits = {}
            today_dividends = {}
            
            for sym, pit_df in point_in_time_universe.items():
                if 'stock splits' in pit_df.columns:
                    today_split = pit_df['stock splits'].iloc[-1]
                    if today_split > 0:
                        today_splits[sym] = today_split
                if 'dividends' in pit_df.columns:
                    today_div = pit_df['dividends'].iloc[-1]
                    if today_div > 0:
                        today_dividends[sym] = today_div
                        
            # Apply Splits
            if today_splits:
                from trading_system.app.data.corporate_actions import CorporateActionProcessor
                new_positions = CorporateActionProcessor.apply_splits_to_portfolio(self.portfolio.get_positions(), today_splits)
                for sym, qty in new_positions.items():
                    if sym in self.portfolio.positions:
                        self.portfolio.positions[sym] = float(qty)
                        
            # Apply Cash Dividends
            if today_dividends:
                for sym, div_per_share in today_dividends.items():
                    shares_held = self.portfolio.get_positions().get(sym, 0)
                    if shares_held > 0:
                        cash_payout = shares_held * div_per_share
                        self.portfolio.cash += cash_payout
                        logger.info(f"CORPORATE ACTION: {sym} paid ${div_per_share} dividend. Added ${cash_payout:.2f} to cash.")
            
            # 3. Strategy evaluates the entire universe and generates cross-sectional signals
            signals = self.strategy.generate_signals(point_in_time_universe)
            
            # 4. Portfolio Construction (Signals -> Target Portfolio Weights)
            target_weights = self.portfolio_constructor.generate_target_weights(signals, point_in_time_universe)
            
            # 5. Order Generation (Compare target weights to current portfolio state)
            total_equity = self.portfolio.cash
            current_positions = self.portfolio.get_positions()
            
            # Estimate total dynamic equity including open positions (Mark-to-Market)
            for sym, qty in current_positions.items():
                if sym in point_in_time_universe and not point_in_time_universe[sym].empty:
                    last_price = point_in_time_universe[sym]['close'].iloc[-1]
                    import math
                    if not math.isnan(last_price):
                        total_equity += (qty * last_price)
                    
            # Record equity curve point for performance analysis
            if not hasattr(self, 'equity_curve'):
                self.equity_curve = {}
            self.equity_curve[current_time] = total_equity
            
            # Ensure any currently held position that is missing from target_weights is explicitly targeted to 0
            for open_sym in current_positions.keys():
                if open_sym not in target_weights:
                    target_weights[open_sym] = 0.0
                    
            # Generate required trades to reach the new target weights
            for sym, target_weight in target_weights.items():
                if target_weight == 'HOLD':
                    continue # Explicit NO TRADE command, preserve current position size
                    
                target_value = total_equity * target_weight
                
                if sym not in point_in_time_universe or point_in_time_universe[sym].empty:
                    continue
                current_price = point_in_time_universe[sym]['close'].iloc[-1]
                
                import math
                if math.isnan(current_price) or current_price <= 0:
                    continue
                    
                current_qty = current_positions.get(sym, 0.0)
                current_value = current_qty * current_price
                
                value_to_trade = target_value - current_value
                if math.isnan(value_to_trade):
                    continue
                qty_to_trade = int(value_to_trade / current_price)
                
                if qty_to_trade != 0:
                    side = "BUY" if qty_to_trade > 0 else "SELL"
                    # V2 Idempotency: Deterministic Order Hash
                    import hashlib
                    order_hash_base = f"{experiment_id}_{current_time.date()}_{sym}_{side}_{qty_to_trade}"
                    deterministic_id = f"V2-{hashlib.md5(order_hash_base.encode()).hexdigest()[:12]}"
                    
                    trade_request = {
                        "client_order_id": deterministic_id,
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
                                price=float(fill['fill_price']),
                                status=fill['status']
                            )
                        if self.db:
                            self.db.add(db_order)
                            
        # Attempt to capture the exact git commit for reproducibility
        import subprocess
        try:
            git_commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
        except Exception:
            git_commit = "unknown"

        # Commit experiment metrics to the rigorous V2 Registry
        exp = Experiment(
            experiment_id=experiment_id,
            strategy_id=self.strategy.__class__.__name__,
            strategy_version="1.0",
            dataset_version="multi-asset-batch",
            git_commit=git_commit,
            universe=",".join(symbols),
            training_period="N/A",
            execution_assumptions={"slippage": "dynamic_simulation", "commission": 0.0},
            parameters={"symbols": symbols},
            metrics={"final_equity": total_equity}
        )
        if self.db:
            self.db.add(exp)
            self.db.commit()
        
        logger.info(f"Multi-Asset Backtest {experiment_id} Complete")
        return self.portfolio
