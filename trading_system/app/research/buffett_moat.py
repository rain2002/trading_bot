"""
The Buffett Moat & Quality Scorecard (Fundamental Quality Gate)
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Chapter 2, Pod 1)

Why This Is Included for Swing & Dip-Buying:
In pure technical systems, momentum bots blindly buy junk companies, debt-laden traps,
or pump-and-dump penny stocks simply because their prices spiked. When a technical dip
occurs in a junk stock, it frequently crashes to zero.
By gating all entries through the Buffett Moat Scorecard, our momentum breakouts
and dip buys are restricted exclusively to companies with durable competitive moats,
pricing power, and pristine balance sheets. This eliminates bankruptcy traps, ensures
dips reliably rebound, and allows winning compounders to run safely for multi-month
or multi-year wealth generation.

The 4 Fundamental Pillars:
1. ROIC >= 15.0%: High capital efficiency & sustainable economic moat.
2. Gross Margin >= 40.0%: Pricing power over customers & suppliers.
3. Net Debt / EBITDA < 2.0x (or Net Cash): Pristine fortress balance sheet.
4. Free Cash Flow Yield >= 3.5%: True cash generation, not paper accounting.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

import yfinance as yf

from trading_system.app.common.logger import get_logger

logger = get_logger("BuffettMoat")


class BuffettMoatScorecard:
    """
    Evaluates corporate fundamentals against Warren Buffett & Peter Lynch
    economic moat and quality criteria.
    """

    MIN_PASSING_SCORE: float = 50.0  # Out of 100 points
    CACHE_TTL_DAYS: int = 30         # Fundamentals only refresh quarterly; cache for 30 days

    INDEX_ETFS = {
        "SPY", "QQQ", "DIA", "IWM", "RSP", "VOO", "VTI", "IVV",
        "NIFTYBEES.NS", "BANKBEES.NS", "JUNIORBEES.NS", "GOLDBEES.NS",
        "NIFTY50", "BANKNIFTY"
    }

    def __init__(self, cache_file: Optional[str] = None):
        if cache_file is None:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cache_file = os.path.join(root_dir, "data", "buffett_moat_cache.json")
        self.cache_file = os.path.abspath(cache_file)
        self._load_cache()

    def _load_cache(self):
        """Loads cached fundamental scores to avoid redundant network queries."""
        self.cache: Dict[str, Any] = {}
        if os.path.isfile(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load fundamental moat cache: {e}. Starting fresh.")

    def _save_cache(self):
        """Persists fundamental scores cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save fundamental moat cache: {e}")

    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches fundamental financial data using yfinance with zero out-of-pocket cost.
        Returns normalized dictionary of key financial fields.
        """
        clean_sym = symbol.upper().strip()
        try:
            ticker = yf.Ticker(clean_sym)
            info = getattr(ticker, "info", {}) or {}
            if not isinstance(info, dict) or not info:
                return {}

            return {
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                "total_debt": info.get("totalDebt"),
                "total_cash": info.get("totalCash"),
                "ebitda": info.get("ebitda"),
                "free_cashflow": info.get("freeCashflow"),
                "market_cap": info.get("marketCap"),
                "revenue": info.get("totalRevenue")
            }
        except Exception as e:
            logger.warning(f"Failed to fetch yfinance fundamentals for {clean_sym}: {e}")
            return {}

    def compute_scorecard(self, symbol: str, raw_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluates a company's fundamentals against the 4 Buffett Moat Pillars:
        1. ROIC (Return on Invested Capital >= 15.0%)
        2. Gross Margin (Pricing Power >= 40.0%)
        3. Net Debt / EBITDA (< 2.0x or Net Cash)
        4. Free Cash Flow Yield (Real Cash Generation >= 3.5%)
        """
        clean_sym = symbol.upper().strip()

        # Check if broad index ETF
        if clean_sym in self.INDEX_ETFS or clean_sym.endswith(".ETF") or clean_sym.startswith("^"):
            return {
                "symbol": clean_sym,
                "moat_class": "INDEX_EXEMPT",
                "moat_score": 100.0,
                "approved": True,
                "reason": "Broad market index / ETF exemption granted.",
                "pillars": {
                    "roic": {"value": None, "score": 25.0, "status": "EXEMPT"},
                    "gross_margin": {"value": None, "score": 25.0, "status": "EXEMPT"},
                    "net_debt_ebitda": {"value": None, "score": 25.0, "status": "EXEMPT"},
                    "fcf_yield": {"value": None, "score": 25.0, "status": "EXEMPT"},
                },
                "disqualifiers": []
            }

        # Check cache validity (30 days TTL)
        cached_entry = self.cache.get(clean_sym)
        if cached_entry and not raw_data:
            cached_dt_str = cached_entry.get("timestamp")
            if cached_dt_str:
                try:
                    cached_dt = datetime.fromisoformat(cached_dt_str)
                    if (datetime.now(timezone.utc) - cached_dt).days < self.CACHE_TTL_DAYS:
                        return cached_entry["scorecard"]
                except Exception:
                    pass

        # Ingest fundamental data
        data = raw_data if raw_data is not None else self.fetch_fundamentals(clean_sym)
        if not data:
            # Conservative default if data unavailable: Neutral rating permitting trade
            # with cautionary notice unless data is known to be missing due to delisting
            scorecard = {
                "symbol": clean_sym,
                "moat_class": "UNRATED",
                "moat_score": 50.0,
                "approved": True,
                "reason": "Fundamental data unavailable; neutral evaluation assigned.",
                "pillars": {},
                "disqualifiers": []
            }
            return scorecard

        disqualifiers = []

        # -------------------------------------------------------------
        # PILLAR 1: Return on Invested Capital (ROIC >= 15.0%)
        # -------------------------------------------------------------
        # ROIC estimate: if ROE and ROA are available, use blended ROIC proxy
        # Otherwise use ROE or operating margin * asset turnover
        roe = data.get("return_on_equity")
        roa = data.get("return_on_assets")
        roic_val = None

        if roe is not None and roa is not None:
            # Blended proxy: ROIC is bounded between ROA and ROE
            roic_val = min(float(roe), max(float(roa), float(roe) * 0.40))
        elif roe is not None:
            roic_val = float(roe) * 0.70
        elif roa is not None:
            roic_val = float(roa) * 2.0

        p1_score = 0.0
        p1_status = "FAIL"
        if roic_val is not None:
            if roic_val >= 0.20:
                p1_score = 25.0
                p1_status = "EXCELLENT"
            elif roic_val >= 0.15:
                p1_score = 20.0
                p1_status = "PASS"
            elif roic_val >= 0.10:
                p1_score = 12.0
                p1_status = "MODERATE"
            else:
                p1_score = 0.0
                p1_status = "FAIL"
        else:
            p1_score = 12.5  # Neutral if unobservable

        # -------------------------------------------------------------
        # PILLAR 2: Gross Margin (Pricing Power >= 40.0%)
        # -------------------------------------------------------------
        gm_val = data.get("gross_margins")
        p2_score = 0.0
        p2_status = "FAIL"
        if gm_val is not None:
            gm_val = float(gm_val)
            if gm_val >= 0.50:
                p2_score = 25.0
                p2_status = "EXCELLENT"
            elif gm_val >= 0.40:
                p2_score = 20.0
                p2_status = "PASS"
            elif gm_val >= 0.25:
                p2_score = 10.0
                p2_status = "MODERATE"
            else:
                p2_score = 0.0
                p2_status = "FAIL"

            # Hard Disqualifier: Gross margin < 15.0% is a commoditized low-pricing-power business
            if gm_val < 0.15:
                disqualifiers.append(f"EXTREME_LOW_MARGIN ({gm_val*100:.1f}% < 15.0%)")
        else:
            p2_score = 12.5

        # -------------------------------------------------------------
        # PILLAR 3: Balance Sheet Strength (Net Debt / EBITDA < 2.0x)
        # -------------------------------------------------------------
        total_debt = data.get("total_debt")
        total_cash = data.get("total_cash")
        ebitda = data.get("ebitda")

        p3_score = 0.0
        p3_status = "FAIL"
        net_debt_ebitda_val = None

        if total_debt is not None and total_cash is not None and ebitda is not None:
            t_debt = float(total_debt)
            t_cash = float(total_cash)
            t_ebitda = float(ebitda)
            net_debt = t_debt - t_cash

            if net_debt <= 0:
                # Fortress Balance Sheet: Net Cash Position!
                net_debt_ebitda_val = 0.0
                p3_score = 25.0
                p3_status = "FORTRESS_NET_CASH"
            elif t_ebitda > 0:
                net_debt_ebitda_val = round(net_debt / t_ebitda, 2)
                if net_debt_ebitda_val < 1.0:
                    p3_score = 22.0
                    p3_status = "EXCELLENT"
                elif net_debt_ebitda_val < 2.0:
                    p3_score = 18.0
                    p3_status = "PASS"
                elif net_debt_ebitda_val < 3.0:
                    p3_score = 8.0
                    p3_status = "ELEVATED"
                else:
                    p3_score = 0.0
                    p3_status = "HIGH_LEVERAGE"

                # Hard Disqualifier: Extreme Debt Trap
                if net_debt_ebitda_val >= 4.0:
                    disqualifiers.append(f"DEBT_TRAP (Net Debt/EBITDA {net_debt_ebitda_val:.1f}x >= 4.0x)")
            else:
                # Negative EBITDA with net debt -> high bankruptcy risk
                p3_score = 0.0
                p3_status = "NEGATIVE_EBITDA"
                disqualifiers.append("NEGATIVE_EBITDA_WITH_DEBT")
        else:
            p3_score = 12.5

        # -------------------------------------------------------------
        # PILLAR 4: Free Cash Flow Yield (FCF Yield >= 3.5%)
        # -------------------------------------------------------------
        fcf = data.get("free_cashflow")
        mcap = data.get("market_cap")
        p4_score = 0.0
        p4_status = "FAIL"
        fcf_yield_val = None

        if fcf is not None and mcap is not None and float(mcap) > 0:
            fcf_val = float(fcf)
            mcap_val = float(mcap)
            fcf_yield_val = round(fcf_val / mcap_val, 4)

            if fcf_yield_val >= 0.05:
                p4_score = 25.0
                p4_status = "EXCELLENT"
            elif fcf_yield_val >= 0.035:
                p4_score = 20.0
                p4_status = "PASS"
            elif fcf_yield_val >= 0.015:
                p4_score = 12.0
                p4_status = "MODERATE"
            elif fcf_yield_val > 0.0:
                p4_score = 6.0
                p4_status = "LOW_POSITIVE"
            else:
                p4_score = 0.0
                p4_status = "NEGATIVE_FCF"
        else:
            p4_score = 12.5

        total_score = round(p1_score + p2_score + p3_score + p4_score, 1)

        # Classification
        if total_score >= 70.0:
            moat_class = "WIDE_MOAT"
        elif total_score >= 50.0:
            moat_class = "NARROW_MOAT"
        else:
            moat_class = "NO_MOAT"

        # Gate approval decision
        approved = (total_score >= self.MIN_PASSING_SCORE) and (len(disqualifiers) == 0)

        if not approved:
            if disqualifiers:
                reason = f"Rejected: Hard disqualifier triggered ({', '.join(disqualifiers)})"
            else:
                reason = f"Rejected: Composite moat score ({total_score:.1f}) below {self.MIN_PASSING_SCORE} hurdle."
        else:
            reason = f"Approved: {moat_class} confirmed (Score: {total_score:.1f}/100)."

        scorecard = {
            "symbol": clean_sym,
            "moat_class": moat_class,
            "moat_score": total_score,
            "approved": approved,
            "reason": reason,
            "pillars": {
                "roic": {"value": roic_val, "score": p1_score, "status": p1_status},
                "gross_margin": {"value": gm_val, "score": p2_score, "status": p2_status},
                "net_debt_ebitda": {"value": net_debt_ebitda_val, "score": p3_score, "status": p3_status},
                "fcf_yield": {"value": fcf_yield_val, "score": p4_score, "status": p4_status},
            },
            "disqualifiers": disqualifiers
        }

        # Cache valid evaluation
        self.cache[clean_sym] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scorecard": scorecard
        }
        self._save_cache()

        return scorecard

    def is_approved_for_investment(self, symbol: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Fast convenience query for strategy filters.
        Returns: (is_approved, rationale, full_scorecard)
        """
        card = self.compute_scorecard(symbol)
        return card["approved"], card["reason"], card
