import pytest
import numpy as np
import pandas as pd
from trading_system.app.research.quant_engine import QuantEngine
from trading_system.app.ml.feature_pipeline import MLFeaturePipeline


def test_quant_engine_loads_ml_alpha_gate():
    """QuantEngine must load the Phase 3 ML Random Forest model and pipeline."""
    engine = QuantEngine(enable_ml_gating=True)
    assert engine.enable_ml_gating is True
    assert engine.ml_model is not None
    assert engine.ml_pipeline is not None
    assert len(engine.ml_model.feature_names_in_) == 18


def test_ml_feature_pipeline_extracts_all_required_columns():
    """Feature pipeline must compute all 18 features expected by the model."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=250, freq="B")
    close = 100.0 + np.cumsum(np.random.normal(0, 1, 250))
    df = pd.DataFrame({
        "open": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1_000_000
    }, index=dates)

    engine = QuantEngine(enable_ml_gating=True)
    feats = engine.ml_pipeline.extract_features(df)
    
    expected_cols = list(engine.ml_model.feature_names_in_)
    for col in expected_cols:
        assert col in feats.columns, f"Missing feature column: {col}"

    latest_feats = feats[expected_cols].iloc[[-1]]
    assert not latest_feats.isna().any().any()

    # Model inference should output a valid probability
    prob = engine.ml_model.predict_proba(latest_feats)[0, 1]
    assert 0.0 <= prob <= 1.0


def test_quant_engine_graceful_fallback_without_ml():
    """When ML gating is disabled, QuantEngine operates normally on Phase 2 heuristics."""
    engine = QuantEngine(enable_ml_gating=False)
    assert engine.enable_ml_gating is False
    assert engine.ml_model is None

    # Test research pipeline with synthetic universe
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    close = 100.0 + np.cumsum(np.random.normal(0.5, 1, 100)) # strong uptrend
    df = pd.DataFrame({
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1_000_000
    }, index=dates)

    # Mock provider returning uptrend data
    class MockProvider:
        def get_data_as_of(self, symbol, current_time):
            return df

    engine.data_provider = MockProvider()
    results = engine.run_nightly_research(["TEST"], pd.Timestamp.now())
    assert isinstance(results, dict)
    assert "momentum" in results
    assert "mean_reversion" in results
