"""
Unit Tests for Fundamental Quality Filter (ROCE + EPS Growth)
=============================================================
Validates:
  1. ROCE >= 15.0% hurdle
  2. Quarterly EPS / Net Profit YoY Growth >= 0.0%
  3. Debt-to-Equity solvency ceiling <= 2.0
  4. Strict point-in-time filing date enforcement (blocks future lookahead)
  5. Causal universe filtering
"""

import pytest
import pandas as pd
from trading_system.app.fundamentals.quality_filter import FundamentalQualityFilter


def test_fundamental_quality_filter_pass(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(min_roce=0.15, min_eps_growth_yoy=0.0, max_debt_to_equity=2.0, cache_file=cache_file)

    financials = {
        "filing_date": "2024-05-15",
        "roce": 0.24,
        "eps_growth_yoy": 0.18,
        "debt_to_equity": 0.35
    }
    res = f_filter.evaluate_quality("TCS", pd.Timestamp("2024-06-01"), financials=financials)
    assert res["is_quality"] is True
    assert "PASS" in res["reason"]
    assert res["roce"] == 0.24
    assert res["eps_growth_yoy"] == 0.18


def test_fundamental_quality_filter_low_roce(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(min_roce=0.15, cache_file=cache_file)

    # 8% ROCE (below 15% threshold)
    financials = {
        "filing_date": "2024-05-15",
        "roce": 0.08,
        "eps_growth_yoy": 0.25,
        "debt_to_equity": 0.50
    }
    res = f_filter.evaluate_quality("LOW_ROCE_CORP", pd.Timestamp("2024-06-01"), financials=financials)
    assert res["is_quality"] is False
    assert "ROCE (8.0%) < 15.0%" in res["reason"]


def test_fundamental_quality_filter_negative_eps(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(min_eps_growth_yoy=0.0, cache_file=cache_file)

    # Negative net profit YoY (-15%)
    financials = {
        "filing_date": "2024-05-15",
        "roce": 0.20,
        "eps_growth_yoy": -0.15,
        "debt_to_equity": 0.20
    }
    res = f_filter.evaluate_quality("DECLINING_EARNINGS", pd.Timestamp("2024-06-01"), financials=financials)
    assert res["is_quality"] is False
    assert "EPS Growth (-15.0%) < 0.0%" in res["reason"]


def test_fundamental_quality_filter_high_debt(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(max_debt_to_equity=2.0, cache_file=cache_file)

    # D/E = 3.5 (over-levered cyclical)
    financials = {
        "filing_date": "2024-05-15",
        "roce": 0.18,
        "eps_growth_yoy": 0.10,
        "debt_to_equity": 3.50
    }
    res = f_filter.evaluate_quality("DEBT_TRAP_CORP", pd.Timestamp("2024-06-01"), financials=financials)
    assert res["is_quality"] is False
    assert "D/E Ratio (3.50) > 2.00" in res["reason"]


def test_fundamental_quality_filter_lookahead_blocked(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(cache_file=cache_file)

    # Filing date is 2024-08-15, but evaluation date is 2024-06-01 (future filing!)
    future_financials = {
        "filing_date": "2024-08-15",
        "roce": 0.30,
        "eps_growth_yoy": 0.50,
        "debt_to_equity": 0.10
    }
    res = f_filter.evaluate_quality("FUTURE_DATA", pd.Timestamp("2024-06-01"), financials=future_financials)
    assert res["is_quality"] is False
    assert "LOOKAHEAD_BLOCKED" in res["reason"]


def test_fundamental_quality_filter_universe(tmp_path):
    cache_file = str(tmp_path / "test_fund_cache.json")
    f_filter = FundamentalQualityFilter(cache_file=cache_file)

    as_of = pd.Timestamp("2024-06-01")
    candidates = ["HIGH_QUALITY.NS", "DEBT_TRAP.NS", "LOW_ROCE.NS"]
    financials_map = {
        "HIGH_QUALITY": {"filing_date": "2024-05-01", "roce": 0.22, "eps_growth_yoy": 0.15, "debt_to_equity": 0.3},
        "DEBT_TRAP": {"filing_date": "2024-05-01", "roce": 0.18, "eps_growth_yoy": 0.10, "debt_to_equity": 4.2},
        "LOW_ROCE": {"filing_date": "2024-05-01", "roce": 0.06, "eps_growth_yoy": 0.05, "debt_to_equity": 0.5}
    }

    filtered = f_filter.filter_universe(candidates, as_of, financials_map=financials_map)
    assert len(filtered) == 1
    assert filtered[0] == "HIGH_QUALITY.NS"
