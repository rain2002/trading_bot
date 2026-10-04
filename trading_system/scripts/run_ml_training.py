import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.data.yfinance_provider import YFinanceDataProvider
from app.features.indicators import FeatureEngine
from app.models.ml_model import MLPipeline
import warnings
warnings.filterwarnings("ignore")

def run():
    provider = YFinanceDataProvider()
    
    # Train the AI on 14 years of historical data (2010 - 2023)
    train_start = datetime(2010, 1, 1)
    train_end = datetime(2023, 12, 31)
    
    # Test the AI on 2 entirely unseen years (2024 - 2025)
    test_start = datetime(2024, 1, 1)
    test_end = datetime(2025, 12, 31)
    
    print("Fetching training data (2010-2023)...")
    df_train = provider.fetch_historical_data("SPY", train_start, train_end)
    
    print("Fetching testing data (2024-2025)...")
    df_test = provider.fetch_historical_data("SPY", test_start, test_end)
    
    print("\nExtracting mathematical features...")
    df_train = FeatureEngine.add_momentum_features(df_train)
    df_train = FeatureEngine.add_volatility_features(df_train)
    df_train = FeatureEngine.add_trend_features(df_train)
    
    df_test = FeatureEngine.add_momentum_features(df_test)
    df_test = FeatureEngine.add_volatility_features(df_test)
    df_test = FeatureEngine.add_trend_features(df_test)
    
    # Target: Will the stock go up at least 1.5% in the next 5 days?
    pipeline = MLPipeline(target_horizon_days=5, target_return_threshold=0.015)
    
    X_train, y_train = pipeline.prepare_dataset(df_train)
    X_test, y_test = pipeline.prepare_dataset(df_test)
    
    pipeline.train(X_train, y_train)
    pipeline.evaluate(X_test, y_test)
    
    pipeline.save_model()

if __name__ == "__main__":
    run()
