"""
Phase 3 Offline Machine Learning Training & Evaluation Script
Trains Random Forest model on 10+ years of engineered features.
Evaluates out-of-sample predictive accuracy and saves the model artifact.
Completely isolated from live production.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.ml.feature_pipeline import MLFeaturePipeline
from trading_system.app.ml.model_trainer import QuantMLTrainer


def run_phase3_ml_training():
    print("\n" + "=" * 70)
    print(">>> PHASE 3: MACHINE LEARNING FEATURE & MODEL TRAINING PIPELINE <<<")
    print("=" * 70)

    # 1. Fetching training data
    provider = YFinanceDataProvider()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 10)  # 10 years of training history

    symbol = "SPY"
    print(f"\n[1/4] Downloading 10 Years of Data for {symbol} ({start_date.date()} to {end_date.date()})...")
    df = provider.fetch_historical_data(symbol, start_date, end_date)

    if df.empty or len(df) < 500:
        print("ERROR: Insufficient data to train ML model.")
        return

    print(f"  Successfully loaded {len(df)} daily bars.")

    # 2. Extracting Features
    print("\n[2/4] Running Quantitative Feature Engineering Pipeline...")
    pipeline = MLFeaturePipeline(forward_prediction_window=5, target_return_threshold=0.005)
    X, y, forward_returns = pipeline.prepare_dataset(df)
    print(f"  Engineered {X.shape[1]} stationary features across {X.shape[0]} samples.")
    print(f"  Feature List: {list(X.columns)}")
    print(f"  Positive Class Balance (Bullish forward 5d): {y.mean()*100:.1f}%")

    # 3. Model Training & Purged Walk-Forward Cross Validation
    print("\n[3/4] Training Random Forest with Chronological Walk-Forward Split (75% Train, 25% Out-of-Sample)...")
    trainer = QuantMLTrainer(n_estimators=150, max_depth=5, min_samples_leaf=20)
    results = trainer.train_walk_forward(X, y, forward_returns, train_ratio=0.75)

    # 4. Display Results
    print("\n" + "=" * 50)
    print(">>> OUT-OF-SAMPLE (UNSEEN FUTURE) ML TEAR SHEET <<<")
    print("=" * 50)
    print(f"  Training Samples         : {results['train_samples']}")
    print(f"  Unseen Test Samples      : {results['test_samples']}")
    print(f"  Test Period              : {results['test_start_date'][:10]} to {results['test_end_date'][:10]}")
    print(f"  Out-of-Sample Accuracy   : {results['out_of_sample_accuracy']*100:.2f}%")
    print(f"  Out-of-Sample Precision  : {results['out_of_sample_precision']*100:.2f}%")
    print(f"  ML Strategy Test Return  : {results['strategy_return_pct']}%")
    print(f"  Buy & Hold Test Return   : {results['buy_and_hold_pct']}%")
    print("-" * 50)
    print("  TOP PREDICTIVE FEATURES IDENTIFIED:")
    for feat, imp in results["top_features"].items():
        print(f"    - {feat.ljust(20)} : {imp*100:5.2f}% importance")
    print("=" * 50)

    # 5. Persist Model Artifact
    model_save_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "models", "quant_rf_model.joblib"
    )
    trainer.save_model(model_save_path)
    print(f"\nTrained ML model successfully saved to: {model_save_path}")
    print("Phase 3 pipeline verified and ready for deployment when server is provisioned!")


if __name__ == "__main__":
    run_phase3_ml_training()
