"""
Unit Tests for Buffett Moat & Quality Scorecard (Chapter 2, Pod 1)
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)
"""

import os
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from trading_system.app.research.buffett_moat import BuffettMoatScorecard


class TestBuffettMoatScorecard:

    def test_wide_moat_prime_compounder(self, tmp_path):
        """
        A stellar compounder (e.g., Apple, Microsoft, TCS) with high ROIC,
        wide gross margins, fortress net cash, and positive FCF should receive
        WIDE_MOAT status and maximum passing score.
        """
        cache_file = str(tmp_path / "moat_cache.json")
        scorecard_engine = BuffettMoatScorecard(cache_file=cache_file)

        mock_data = {
            "gross_margins": 0.48,           # 48% GM (Pillar 2: >= 40%)
            "operating_margins": 0.30,
            "return_on_equity": 0.40,        # High ROE / ROIC (Pillar 1: >= 15%)
            "return_on_assets": 0.20,
            "total_debt": 50000000.0,
            "total_cash": 80000000.0,        # Net Cash! (Pillar 3: Fortress)
            "ebitda": 100000000.0,
            "free_cashflow": 60000000.0,
            "market_cap": 1000000000.0       # FCF Yield = 6.0% (Pillar 4: >= 3.5%)
        }

        card = scorecard_engine.compute_scorecard("COMPOUNDER", raw_data=mock_data)

        assert card["approved"] is True
        assert card["moat_class"] == "WIDE_MOAT"
        assert card["moat_score"] >= 85.0
        assert card["pillars"]["net_debt_ebitda"]["status"] == "FORTRESS_NET_CASH"
        assert card["pillars"]["gross_margin"]["status"] == "PASS" or card["pillars"]["gross_margin"]["status"] == "EXCELLENT"
        assert len(card["disqualifiers"]) == 0

    def test_extreme_debt_trap_disqualified(self, tmp_path):
        """
        Companies with excessive debt (Net Debt / EBITDA >= 4.0x) must be
        disqualified regardless of other metrics.
        """
        cache_file = str(tmp_path / "moat_cache.json")
        scorecard_engine = BuffettMoatScorecard(cache_file=cache_file)

        mock_data = {
            "gross_margins": 0.45,
            "operating_margins": 0.10,
            "return_on_equity": 0.12,
            "return_on_assets": 0.04,
            "total_debt": 500000000.0,       # $500M Debt
            "total_cash": 20000000.0,        # $20M Cash -> Net Debt = $480M
            "ebitda": 100000000.0,           # EBITDA = $100M -> Ratio = 4.8x (Debt Trap!)
            "free_cashflow": 10000000.0,
            "market_cap": 200000000.0
        }

        card = scorecard_engine.compute_scorecard("DEBT_TRAP_INC", raw_data=mock_data)

        assert card["approved"] is False
        assert any("DEBT_TRAP" in d for d in card["disqualifiers"])
        assert "Rejected" in card["reason"]

    def test_low_gross_margin_commodity_disqualified(self, tmp_path):
        """
        Companies with commoditized margins (< 15.0%) lack pricing power and must be rejected.
        """
        cache_file = str(tmp_path / "moat_cache.json")
        scorecard_engine = BuffettMoatScorecard(cache_file=cache_file)

        mock_data = {
            "gross_margins": 0.08,           # 8% Gross Margin (< 15%)
            "operating_margins": 0.02,
            "return_on_equity": 0.05,
            "return_on_assets": 0.02,
            "total_debt": 10000000.0,
            "total_cash": 20000000.0,
            "ebitda": 20000000.0,
            "free_cashflow": 5000000.0,
            "market_cap": 200000000.0
        }

        card = scorecard_engine.compute_scorecard("COMMODITY_CORP", raw_data=mock_data)

        assert card["approved"] is False
        assert any("EXTREME_LOW_MARGIN" in d for d in card["disqualifiers"])

    def test_broad_market_etf_exemption(self, tmp_path):
        """
        Broad market indexes and ETFs (SPY, QQQ, NIFTYBEES.NS) must be auto-exempted
        from corporate fundamental filings and granted full approval.
        """
        cache_file = str(tmp_path / "moat_cache.json")
        scorecard_engine = BuffettMoatScorecard(cache_file=cache_file)

        for etf in ["SPY", "QQQ", "NIFTYBEES.NS"]:
            card = scorecard_engine.compute_scorecard(etf)
            assert card["approved"] is True
            assert card["moat_class"] == "INDEX_EXEMPT"
            assert card["moat_score"] == 100.0

    def test_caching_mechanism(self, tmp_path):
        """
        Verifies fundamental scorecard results are cached to disk with TTL.
        """
        cache_file = str(tmp_path / "moat_cache.json")
        scorecard_engine = BuffettMoatScorecard(cache_file=cache_file)

        mock_data = {
            "gross_margins": 0.42,
            "operating_margins": 0.22,
            "return_on_equity": 0.25,
            "return_on_assets": 0.12,
            "total_debt": 10000000.0,
            "total_cash": 30000000.0,
            "ebitda": 40000000.0,
            "free_cashflow": 30000000.0,
            "market_cap": 500000000.0
        }

        # First evaluation computes and caches
        card1 = scorecard_engine.compute_scorecard("CACHED_STOCK", raw_data=mock_data)
        assert os.path.exists(cache_file)

        # Second evaluation reads from cache (with no raw_data and mock fetch returning empty)
        with patch.object(scorecard_engine, "fetch_fundamentals", return_value={}):
            card2 = scorecard_engine.compute_scorecard("CACHED_STOCK")
            assert card2["symbol"] == "CACHED_STOCK"
            assert card2["moat_score"] == card1["moat_score"]

    def test_quant_engine_filters_candidates_with_moat_scorecard(self):
        """
        Verifies that QuantEngine.run_nightly_research consults BuffettMoatScorecard,
        vetoing disqualified symbols and annotating approved compounders with their moat scores.
        """
        import pandas as pd
        import numpy as np
        from trading_system.app.research.quant_engine import QuantEngine

        brain = QuantEngine(enable_ml_gating=False, moat_mode="gate")

        # Create mock bullish data for two symbols
        dates = pd.date_range("2026-01-01", periods=100, freq="D")
        prices_uptrend = np.linspace(100, 200, 100)
        df_uptrend = pd.DataFrame({
            "open": prices_uptrend * 0.99,
            "high": prices_uptrend * 1.01,
            "low": prices_uptrend * 0.98,
            "close": prices_uptrend,
            "volume": 1000000
        }, index=dates)

        with patch.object(brain.data_provider, "get_data_as_of", return_value=df_uptrend):
            # Mock moat scorecard approvals: APPROVED_MOAT passes, JUNK_DEBT fails
            def mock_moat_eval(sym):
                if sym == "APPROVED_MOAT":
                    return True, "Wide Moat", {"moat_class": "WIDE_MOAT", "moat_score": 88.0}
                return False, "Extreme Debt Trap", {"moat_class": "NO_MOAT", "moat_score": 20.0}

            with patch.object(brain.moat_scorecard, "is_approved_for_investment", side_effect=mock_moat_eval):
                results = brain.run_nightly_research(["APPROVED_MOAT", "JUNK_DEBT"], datetime.now())

                mom_symbols = [s["symbol"] for s in results["momentum"]]
                assert "APPROVED_MOAT" in mom_symbols
                assert "JUNK_DEBT" not in mom_symbols

                approved_signal = next(s for s in results["momentum"] if s["symbol"] == "APPROVED_MOAT")
                assert approved_signal["moat_class"] == "WIDE_MOAT"
                assert approved_signal["moat_score"] == 88.0
                assert "Moat: WIDE_MOAT" in approved_signal["rationale"]
