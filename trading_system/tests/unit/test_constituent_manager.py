"""
Unit Tests for Point-in-Time Index Constituent Manager
Verifies:
  1. Symbol normalization (. to -).
  2. Addition tracking (e.g. TSLA not in S&P 500 before Dec 2020).
  3. Active membership querying on arbitrary dates.
  4. Non-leakage / point-in-time index queries.
"""

import os
import pytest
import pandas as pd
from trading_system.app.data.constituent_manager import PointInTimeConstituentManager


@pytest.fixture
def constituent_mgr():
    mgr = PointInTimeConstituentManager()
    assert mgr._is_loaded, "Constituent manager should load change records."
    return mgr


def test_symbol_normalization():
    assert PointInTimeConstituentManager.normalize_symbol("brk.b") == "BRK-B"
    assert PointInTimeConstituentManager.normalize_symbol("BF.B") == "BF-B"
    assert PointInTimeConstituentManager.normalize_symbol("AAPL") == "AAPL"


def test_historical_additions_tsla(constituent_mgr):
    # Tesla (TSLA) was added to the S&P 500 on December 21, 2020.
    date_before = pd.to_datetime("2020-12-15")
    date_after = pd.to_datetime("2020-12-22")

    assert not constituent_mgr.is_constituent("TSLA", date_before), "TSLA should not be in S&P 500 before Dec 21, 2020"
    assert constituent_mgr.is_constituent("TSLA", date_after), "TSLA should be in S&P 500 after Dec 21, 2020"


def test_historical_additions_goog(constituent_mgr):
    # Google (GOOG/GOOGL) was added in April 2006.
    date_2000 = pd.to_datetime("2000-01-03")
    date_2010 = pd.to_datetime("2010-01-04")

    assert not constituent_mgr.is_constituent("GOOG", date_2000), "Google did not exist in S&P 500 in 2000"
    assert not constituent_mgr.is_constituent("GOOGL", date_2000), "Google did not exist in S&P 500 in 2000"
    assert constituent_mgr.is_constituent("GOOGL", date_2010), "GOOGL should be in S&P 500 in 2010"


def test_active_constituents_count(constituent_mgr):
    date_2015 = pd.to_datetime("2015-06-15")
    constituents = constituent_mgr.get_active_constituents(date_2015)
    # S&P 500 has around 500-505 constituents depending on share classes
    assert 490 <= len(constituents) <= 510
    assert "AAPL" in constituents
    assert "MSFT" in constituents

def test_nifty50_pit_constituents_manager():
    """Verify strict point-in-time constituent membership for NSE Nifty 50 universe."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    changes_csv = os.path.join(base_dir, "nifty50_historical_components_changes.csv")
    se_csv = os.path.join(base_dir, "nifty50_ticker_start_end.csv")

    assert os.path.exists(changes_csv), f"Missing {changes_csv}"
    assert os.path.exists(se_csv), f"Missing {se_csv}"

    mgr = PointInTimeConstituentManager(changes_csv_path=changes_csv, start_end_csv_path=se_csv)
    assert mgr._is_loaded, "Nifty 50 PIT manager should load datasets"

    # 1. Exactly 50 members on any arbitrary date
    for dt_str in ["2008-01-15", "2013-05-20", "2018-11-10", "2024-10-15"]:
        c = mgr.get_active_constituents(pd.to_datetime(dt_str))
        assert len(c) == 50, f"Expected exactly 50 active constituents on {dt_str}, got {len(c)}"

    # 2. Historical distressed / removed names (Suzlon, Yes Bank, RCOM)
    assert mgr.is_constituent("SUZLON.NS", pd.to_datetime("2008-06-01"))
    assert not mgr.is_constituent("SUZLON.NS", pd.to_datetime("2012-01-01"))

    assert mgr.is_constituent("YESBANK.NS", pd.to_datetime("2018-01-01"))
    assert not mgr.is_constituent("YESBANK.NS", pd.to_datetime("2020-05-01"))

    # 3. Modern additions (Trent, BEL, Adani Enterprises)
    assert not mgr.is_constituent("TRENT.NS", pd.to_datetime("2023-01-01"))
    assert mgr.is_constituent("TRENT.NS", pd.to_datetime("2024-10-01"))

    assert not mgr.is_constituent("BEL.NS", pd.to_datetime("2024-01-01"))
    assert mgr.is_constituent("BEL.NS", pd.to_datetime("2024-10-01"))

    assert not mgr.is_constituent("ADANIENT.NS", pd.to_datetime("2021-01-01"))
    assert mgr.is_constituent("ADANIENT.NS", pd.to_datetime("2022-10-15"))
