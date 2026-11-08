"""
Unit Test: Corporate Action Adjustment vs Market Crash & ETF ISIN Guard
=======================================================================
P0 Fix 1 & Fix 4 Invariants:
1. Known 10:1 split yields ~0% adjusted return on the ex-date.
2. A real -50% overnight market crash (without corporate action) strictly STAYS -50%,
   and is NEVER erased or misclassified as a 2:1 split.
3. ISIN filtering strictly preserves 'INE' (Indian Equities) and excludes 'INF' (ETFs/Funds).
4. ETF ticker filter identifies ETF symbols (e.g. GOLDBEES, NIFTYBEES, LIQUIDBEES).
5. All 15 historical splits used in simulation are verified in the audited circulars registry.
"""

import pytest
import pandas as pd
import numpy as np

from trading_system.app.data.corporate_actions import (
    load_audited_corporate_actions,
    get_corporate_action_multiplier,
    is_valid_equity_isin,
    is_etf_ticker,
    build_verified_split_adjustment_matrix
)


def test_verified_10_to_1_split_gives_zero_adjusted_return():
    """
    On 2016-09-08, BAJFINANCE underwent a 5:1 split plus a 1:1 bonus (effective 10:1 ratio).
    Unadjusted price dropped from ~Rs 10,700 to ~Rs 1,070 (-90% raw gap).
    The verified corporate action multiplier (10.0) must adjust historical price so adjusted return is ~0%.
    """
    ex_date = "2016-09-08"
    symbol = "BAJFINANCE"
    mult = get_corporate_action_multiplier(ex_date, symbol)
    assert mult == 10.0, f"Expected 10.0 multiplier for BAJFINANCE on {ex_date}, got {mult}"

    dates = pd.date_range("2016-09-07", "2016-09-08")
    raw_close = pd.DataFrame({
        "BAJFINANCE": [10700.0, 1070.0]
    }, index=dates)

    mult_df, adj_factors = build_verified_split_adjustment_matrix(raw_close)
    adj_close = raw_close * adj_factors

    # Pre-split close (2016-09-07) was 10700 * 0.1 = 1070.0 in adjusted terms
    # Post-split close (2016-09-08) is 1070.0 * 1.0 = 1070.0
    adj_ret = (adj_close.iloc[1] - adj_close.iloc[0]) / adj_close.iloc[0]
    assert np.isclose(adj_ret["BAJFINANCE"], 0.0, atol=1e-5), f"Expected 0% return, got {adj_ret['BAJFINANCE']}"


def test_real_50_percent_crash_stays_negative_50_percent():
    """
    A market crash or fundamental fraud where a stock gaps down -50% overnight
    (e.g., Satyam, DHFL, Yes Bank) without an official corporate action MUST NOT be
    classified as a 2:1 split. Its return MUST remain -50%.
    """
    crash_date = "2020-03-12"
    symbol = "CRASH_STOCK"
    mult = get_corporate_action_multiplier(crash_date, symbol)
    assert mult == 1.0, f"Unregistered event must return 1.0 multiplier, got {mult}"

    dates = pd.date_range("2020-03-11", "2020-03-12")
    raw_close = pd.DataFrame({
        "CRASH_STOCK": [1000.0, 500.0]  # Exact -50% crash
    }, index=dates)

    mult_df, adj_factors = build_verified_split_adjustment_matrix(raw_close)
    adj_close = raw_close * adj_factors

    # Adjusted series must NOT change
    ret = (adj_close.iloc[1] - adj_close.iloc[0]) / adj_close.iloc[0]
    assert np.isclose(ret["CRASH_STOCK"], -0.50, atol=1e-5), f"Crash was incorrectly altered! Got {ret['CRASH_STOCK']}"


def test_isin_filtering_ine_vs_inf():
    """
    P0 Fix 4: Indian Equities have ISINs starting with 'INE'.
    ETFs, Mutual Funds, and Sovereign Gold Bonds start with 'INF' or 'IN9'.
    Only 'INE' must pass equity validation.
    """
    # Valid Equities
    assert is_valid_equity_isin("INE296A01024") is True   # BAJFINANCE
    assert is_valid_equity_isin("INE002A01018") is True   # RELIANCE
    assert is_valid_equity_isin("INE467B01029") is True   # TCS
    assert is_valid_equity_isin("INE280A01028") is True   # TITAN

    # Invalid Non-Equities (ETFs, Funds)
    assert is_valid_equity_isin("INF732E01037") is False  # NIFTYBEES
    assert is_valid_equity_isin("INF209K01166") is False  # CPSE ETF
    assert is_valid_equity_isin("INF204KB14I2") is False  # Nippon India ETF
    assert is_valid_equity_isin("IN9002A01018") is False  # Partly paid


def test_etf_ticker_regex_filtering():
    """
    Tests identification of ETF tickers by symbol pattern.
    """
    # ETFs
    assert is_etf_ticker("GOLDBEES") is True
    assert is_etf_ticker("NIFTYBEES") is True
    assert is_etf_ticker("LIQUIDBEES") is True
    assert is_etf_ticker("JUNIORBEES") is True
    assert is_etf_ticker("SETFNIF50") is True
    assert is_etf_ticker("MOM100ETF") is True
    assert is_etf_ticker("AUTOBEES.NS") is True

    # Real stocks
    assert is_etf_ticker("RELIANCE") is False
    assert is_etf_ticker("TCS") is False
    assert is_etf_ticker("BAJFINANCE") is False
    assert is_etf_ticker("TITAN") is False
    assert is_etf_ticker("HDFCBANK.NS") is False


def test_all_15_detected_splits_verified_in_registry():
    """
    Verifies that each of the 15 corporate actions detected in the 17-year simulation
    exists in the audited registry with the verified corporate action multiplier.
    """
    expected_actions = [
        ("2010-08-27", "LUPIN", 5.0),
        ("2010-09-08", "TVSMOTOR", 2.0),
        ("2011-06-23", "TITAN", 20.0),
        ("2011-10-31", "VIPIND", 5.0),
        ("2012-05-25", "GRAVITA", 5.0),
        ("2013-07-29", "SUNPHARMA", 2.0),
        ("2014-06-03", "MINDTREE", 2.0),
        ("2015-03-19", "TECHM", 4.0),
        ("2015-07-20", "AUROPHARMA", 2.0),
        ("2016-09-08", "BAJFINANCE", 10.0),
        ("2017-01-04", "JSWSTEEL", 10.0),
        ("2017-07-03", "PETRONET", 2.0),
        ("2021-03-18", "DIXON", 5.0),
        ("2021-12-03", "IEX", 3.0),
        ("2023-09-28", "HAL", 2.0),
    ]

    actions_cache = load_audited_corporate_actions()
    for dt, sym, expected_mult in expected_actions:
        mult = get_corporate_action_multiplier(dt, sym)
        assert mult == expected_mult, (
            f"Action mismatch for {sym} on {dt}: expected {expected_mult}, found {mult}"
        )
