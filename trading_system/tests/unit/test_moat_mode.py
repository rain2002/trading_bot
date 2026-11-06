"""
Unit Tests for Buffett Moat Scorecard Modes: Shadow vs Gate (Fix 3).
Verifies:
1. Shadow Mode: logs the scorecard and attaches moat_score to signal, letting the trade through.
2. Gate Mode: strictly vetoes the trade when moat score fails the hurdle.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import pandas as pd
import numpy as np

from trading_system.app.research.quant_engine import QuantEngine


def create_mock_uptrend_df(n_bars: int = 100) -> pd.DataFrame:
    """Creates a strong upward trending DataFrame for mock testing."""
    dates = pd.date_range(end=datetime.now(), periods=n_bars, freq="D")
    base_price = 100.0
    # Consistently increasing prices
    prices = [base_price + (i * 1.5) for i in range(n_bars)]
    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000000] * n_bars
    }, index=dates)
    return df


def test_moat_shadow_mode_lets_trade_through():
    """
    In 'shadow' mode: A stock failing the moat hurdle is logged and evaluated,
    and its signal is NOT vetoed. The moat_score is attached to the output signal.
    """
    engine = QuantEngine(enable_ml_gating=False, moat_mode="shadow")

    # Mock data provider to return strong uptrending data
    mock_df = create_mock_uptrend_df()
    engine.data_provider.get_data_as_of = MagicMock(return_value=mock_df)

    # Mock failing moat scorecard (Composite score 42.0, NO_MOAT)
    engine.moat_scorecard.is_approved_for_investment = MagicMock(
        return_value=(
            False,
            "Rejected: Composite moat score (42.0) below 70.0 hurdle.",
            {"moat_score": 42.0, "moat_class": "NO_MOAT"}
        )
    )

    signals = engine.run_nightly_research(universe=["TEST_TICKER"], as_of_time=datetime.now())

    # Shadow mode MUST let the candidate through
    all_signals = signals["momentum"] + signals["mean_reversion"]
    assert len(all_signals) >= 1, "Shadow mode must allow candidate through despite failing moat hurdle"

    sig = all_signals[0]
    assert sig["symbol"] == "TEST_TICKER"
    assert sig["moat_score"] == 42.0, "Moat score must be attached to signal"
    assert sig["moat_class"] == "NO_MOAT"


def test_moat_gate_mode_vetoes_trade():
    """
    In 'gate' mode: A stock failing the moat hurdle is strictly vetoed.
    No signals may be generated for this candidate.
    """
    engine = QuantEngine(enable_ml_gating=False, moat_mode="gate")

    mock_df = create_mock_uptrend_df()
    engine.data_provider.get_data_as_of = MagicMock(return_value=mock_df)

    # Failing moat scorecard
    engine.moat_scorecard.is_approved_for_investment = MagicMock(
        return_value=(
            False,
            "Rejected: Composite moat score (42.0) below 70.0 hurdle.",
            {"moat_score": 42.0, "moat_class": "NO_MOAT"}
        )
    )

    signals = engine.run_nightly_research(universe=["TEST_TICKER"], as_of_time=datetime.now())

    # Gate mode MUST veto the candidate completely
    assert len(signals["momentum"]) == 0, "Gate mode must veto momentum signal on failing moat"
    assert len(signals["mean_reversion"]) == 0, "Gate mode must veto mean reversion signal on failing moat"
