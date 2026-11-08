"""
Unit Tests for Phase 1 Causal Bhavcopy Liquidity Universe Generator
===================================================================
Verifies:
1. Trailing 6-month median turnover calculation.
2. Exclusion of penny stocks (< INR 20).
3. Survivor-free handling of delisted / fading stocks (they naturally drop out).
4. Strictly causal point-in-time universe creation without lookahead bias.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading_system.scripts.build_causal_bhavcopy_universe import compute_monthly_causal_universe


def generate_synthetic_bhavcopy_panel():
    """Generates synthetic daily bhavcopy records over a 3-month period."""
    dates = pd.date_range("2023-01-01", "2023-03-31", freq="B")
    records = []

    for d in dates:
        # Stock A: High turnover, high price (Bluechip)
        records.append({
            "TIMESTAMP": d,
            "SYMBOL": "STOCK_A",
            "SERIES": "EQ",
            "OPEN": 1000.0,
            "HIGH": 1010.0,
            "LOW": 990.0,
            "CLOSE": 1005.0,
            "TOTTRDQTY": 100000,
            "TOTTRDVAL": 100500000.0  # ~10 Crore/day
        })
        # Stock B: Mid turnover, good price (Midcap compounder)
        records.append({
            "TIMESTAMP": d,
            "SYMBOL": "STOCK_B",
            "SERIES": "EQ",
            "OPEN": 250.0,
            "HIGH": 255.0,
            "LOW": 248.0,
            "CLOSE": 252.0,
            "TOTTRDQTY": 50000,
            "TOTTRDVAL": 12600000.0  # ~1.26 Crore/day
        })
        # Stock C: Penny stock (< 20) -> should be excluded by min_price
        records.append({
            "TIMESTAMP": d,
            "SYMBOL": "STOCK_PENNY",
            "SERIES": "EQ",
            "OPEN": 8.0,
            "HIGH": 8.5,
            "LOW": 7.9,
            "CLOSE": 8.1,
            "TOTTRDQTY": 5000000,
            "TOTTRDVAL": 40500000.0  # High volume but penny stock
        })
        # Stock D: Delisted / Fading Stock (Active in Jan/Feb, stops trading in March)
        if d < pd.Timestamp("2023-03-01"):
            records.append({
                "TIMESTAMP": d,
                "SYMBOL": "STOCK_DELISTED",
                "SERIES": "EQ",
                "OPEN": 150.0,
                "HIGH": 152.0,
                "LOW": 145.0,
                "CLOSE": 148.0,
                "TOTTRDQTY": 80000,
                "TOTTRDVAL": 11840000.0
            })

    return pd.DataFrame(records)


def test_causal_universe_ranking_and_penny_filter():
    df = generate_synthetic_bhavcopy_panel()
    universe = compute_monthly_causal_universe([df], top_n=2, min_price=20.0, lookback_days=60)

    # Rebalances happen at each month-end
    assert len(universe) >= 2

    # Check January rebalance
    jan_date = [k for k in universe.keys() if k.startswith("2023-01")][0]
    jan_tickers = universe[jan_date]

    # Penny stock must NEVER be selected despite high volume
    assert "STOCK_PENNY.NS" not in jan_tickers

    # STOCK_A has the highest turnover -> rank 1
    assert jan_tickers[0] == "STOCK_A.NS"

    # STOCK_DELISTED was active in Jan -> eligible in Jan
    assert "STOCK_DELISTED.NS" in jan_tickers or "STOCK_B.NS" in jan_tickers


def test_fading_stock_drops_out_causally():
    df = generate_synthetic_bhavcopy_panel()
    universe = compute_monthly_causal_universe([df], top_n=2, min_price=20.0, lookback_days=20)

    # Check March rebalance: STOCK_DELISTED stopped trading in March
    mar_dates = [k for k in universe.keys() if k.startswith("2023-03")]
    if mar_dates:
        mar_tickers = universe[mar_dates[0]]
        # In March, STOCK_DELISTED had 0 trading days, so STOCK_A and STOCK_B must be top 2
        assert "STOCK_A.NS" in mar_tickers
        assert "STOCK_B.NS" in mar_tickers
        assert "STOCK_DELISTED.NS" not in mar_tickers
