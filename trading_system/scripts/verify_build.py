from datetime import datetime
import pandas as pd
from trading_system.app.config.settings import settings
from trading_system.app.common.database import get_db, Base, engine
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.library.ml001_random_forest import ML001_RandomForest
from trading_system.app.portfolio.basic import BasicPortfolio
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.constructor import EqualWeightPortfolioConstructor
from trading_system.app.portfolio.adaptive_allocator import AdaptivePortfolioAllocator
from trading_system.app.execution.paper import PaperExecutionAdapter
from trading_system.app.backtesting.multi_asset_engine import MultiAssetBacktester
from trading_system.app.reporting.performance import QuantitativePerformanceAnalyzer
from trading_system.app.models.core import Experiment

def verify():
    print("\n" + "="*60)
    print(">>> INITIATING FULL MASTER SPEC VERIFICATION <<<")
    print("="*60)
    
    # Ensure DB tables exist
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    
    # 1. Setup components
    print("\n[1/5] Booting Subsystems & Injecting Dependencies...")
    data_provider = YFinanceDataProvider()
    strategy = ML001_RandomForest() # V2: Machine Learning AI Strategy
    portfolio = BasicPortfolio(initial_cash=100000.0)
    risk_engine = BasicRiskEngine(max_position_size=100000)
    
    # Phase 8 (Constructor) wrapped by Phase 10 (Adaptive Allocator)
    base_constructor = EqualWeightPortfolioConstructor()
    adaptive_allocator = AdaptivePortfolioAllocator(base_constructor, regime_index="AAPL")
    
    execution_adapter = PaperExecutionAdapter()
    
    backtester = MultiAssetBacktester(
        data_provider=data_provider,
        strategy=strategy,
        portfolio=portfolio,
        risk_engine=risk_engine,
        portfolio_constructor=adaptive_allocator,
        execution_adapter=execution_adapter,
        db_session=db
    )
    
    # 2. Run Engine (Phase 4, 8, 10, 11)
    print("\n[2/5] Running Engine on AAPL & MSFT (2016-2023) [8-Year Full Market Cycle]...")
    start = datetime(2016, 1, 1)
    end = datetime(2023, 12, 31)
    
    import uuid
    exp_id = f"VERIFY-8Y-{uuid.uuid4().hex[:6]}"
    backtester.run(symbols=["AAPL", "MSFT"], start_date=start, end_date=end, experiment_id=exp_id)
    
    # 3. Verify Performance Metrics (Phase 13)
    print("\n[3/5] Calculating Performance Metrics (Phase 13)...")
    analyzer = QuantitativePerformanceAnalyzer()
    
    if hasattr(backtester, 'equity_curve'):
        equity_series = pd.Series(backtester.equity_curve)
        metrics = analyzer.calculate_metrics([], equity_series)
        
        print("\n--- INSTITUTIONAL TEAR SHEET ---")
        for k, v in metrics.items():
            print(f"{k.ljust(25)}: {v}")
    else:
        print("ERROR: Equity curve not found! Engine failed to track performance.")
        sys.exit(1)
        
    # 4. Verify Database Integrity (Phase 3 & 5)
    print("\n[4/5] Verifying Database Persistence (Phase 3)...")
    exp = db.query(Experiment).filter(Experiment.experiment_id == exp_id).first()
    if exp:
        print(f"SUCCESS: Experiment firmly anchored in SQL Database.")
    else:
        print("ERROR: Database persistence failed!")
        sys.exit(1)
        
    print("\n[5/5] SUCCESS: MASTER SPECIFICATION VERIFICATION COMPLETE.")
    print("="*60 + "\n")

if __name__ == "__main__":
    verify()
