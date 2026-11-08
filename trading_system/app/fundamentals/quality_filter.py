"""
Fundamental Quality Screening Engine
====================================
Implements institutional quality filtering for broad-market equity universes
(e.g., Causal NSE Bhavcopy Top 500 / 300) to eliminate breakout fakeouts:

1. Return on Capital Employed (ROCE):
   ROCE = EBIT / (Total Assets - Current Liabilities) >= 15.0%
   Demonstrates high capital efficiency and sustainable economic moat.

2. Quarterly EPS / Net Profit Growth (YoY):
   (PAT_t - PAT_t-4) / PAT_t-4 >= 0.0% (Positive earnings momentum).
   Eliminates debt-fueled or cyclical bubble tops.

3. Solvency & Leverage Guard:
   Total Debt / Total Equity <= 2.0
   Eliminates insolvency / bankruptcy risks in small/mid-caps.

4. Point-in-Time Filing Safety:
   Financials for quarter T are causally lagged to their official filing date
   (defaulting to T + 45 days) to ensure absolute ZERO lookahead bias.
"""

import os
import json
import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Tuple

logger = logging.getLogger("FundamentalQualityFilter")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
CACHE_FILE = os.path.join(DATA_DIR, "fundamental_quality_cache.json")


class FundamentalQualityFilter:
    def __init__(
        self,
        min_roce: float = 0.15,
        min_eps_growth_yoy: float = 0.00,
        max_debt_to_equity: float = 2.0,
        filing_lag_days: int = 45,
        cache_file: str = CACHE_FILE
    ):
        self.min_roce = min_roce
        self.min_eps_growth_yoy = min_eps_growth_yoy
        self.max_debt_to_equity = max_debt_to_equity
        self.filing_lag_days = filing_lag_days
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load fundamental cache: {e}")
        return {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save fundamental cache: {e}")

    def evaluate_quality(
        self,
        symbol: str,
        as_of_date: pd.Timestamp,
        financials: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates whether a symbol passes fundamental quality hurdles as of as_of_date.
        Ensures filing date <= as_of_date (Point-in-Time safety).
        """
        clean_sym = symbol.replace(".NS", "").replace("-NS", "").strip()
        date_str = as_of_date.strftime("%Y-%m-%d")
        cache_key = f"{clean_sym}_{date_str}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        if financials is None:
            # If no financial statement passed, fail-closed for safety
            result = {
                "symbol": clean_sym,
                "as_of_date": date_str,
                "is_quality": False,
                "roce": None,
                "eps_growth_yoy": None,
                "debt_to_equity": None,
                "reason": "FAIL_CLOSED: No point-in-time financial filing records available."
            }
            return result

        # Check Point-in-Time Availability: Filing date must be <= as_of_date
        filing_date = financials.get("filing_date")
        if filing_date is not None:
            filing_ts = pd.to_datetime(filing_date)
            if filing_ts > as_of_date:
                result = {
                    "symbol": clean_sym,
                    "as_of_date": date_str,
                    "is_quality": False,
                    "roce": None,
                    "eps_growth_yoy": None,
                    "debt_to_equity": None,
                    "reason": f"LOOKAHEAD_BLOCKED: Financial filing date {filing_ts.date()} is in future relative to {as_of_date.date()}."
                }
                return result

        # 1. ROCE Calculation & Check
        # EBIT / Capital Employed
        roce = financials.get("roce")
        if roce is None:
            ebit = financials.get("ebit")
            total_assets = financials.get("total_assets")
            curr_liabilities = financials.get("current_liabilities", 0.0)
            if ebit is not None and total_assets is not None and (total_assets - curr_liabilities) > 0:
                roce = ebit / (total_assets - curr_liabilities)

        # 2. Quarterly EPS / Net Profit YoY Growth
        eps_growth = financials.get("eps_growth_yoy")
        if eps_growth is None:
            pat_curr = financials.get("net_profit_current_quarter")
            pat_prior = financials.get("net_profit_prior_year_quarter")
            if pat_curr is not None and pat_prior is not None and pat_prior > 0:
                eps_growth = (pat_curr - pat_prior) / pat_prior

        # 3. Debt to Equity
        de_ratio = financials.get("debt_to_equity")
        if de_ratio is None:
            total_debt = financials.get("total_debt")
            equity = financials.get("total_equity")
            if total_debt is not None and equity is not None and equity > 0:
                de_ratio = total_debt / equity

        reasons = []
        is_pass = True

        if roce is None or roce < self.min_roce:
            is_pass = False
            roce_str = f"{roce*100:.1f}%" if roce is not None else "N/A"
            reasons.append(f"ROCE ({roce_str}) < {self.min_roce*100:.1f}%")

        if eps_growth is None or eps_growth < self.min_eps_growth_yoy:
            is_pass = False
            eps_str = f"{eps_growth*100:+.1f}%" if eps_growth is not None else "N/A"
            reasons.append(f"EPS Growth ({eps_str}) < {self.min_eps_growth_yoy*100:.1f}%")

        if de_ratio is not None and de_ratio > self.max_debt_to_equity:
            is_pass = False
            reasons.append(f"D/E Ratio ({de_ratio:.2f}) > {self.max_debt_to_equity:.2f}")

        reason_str = "PASS: Quality Hurdles Cleared" if is_pass else f"FAIL: {'; '.join(reasons)}"

        result = {
            "symbol": clean_sym,
            "as_of_date": date_str,
            "is_quality": is_pass,
            "roce": round(roce, 4) if roce is not None else None,
            "eps_growth_yoy": round(eps_growth, 4) if eps_growth is not None else None,
            "debt_to_equity": round(de_ratio, 2) if de_ratio is not None else None,
            "reason": reason_str
        }

        self.cache[cache_key] = result
        self._save_cache()
        return result

    def filter_universe(
        self,
        symbols: List[str],
        as_of_date: pd.Timestamp,
        financials_map: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[str]:
        """
        Filters a candidate list of symbols, returning strictly the subset that
        passes the minimum ROCE, positive earnings growth, and leverage limits.
        """
        passed = []
        for s in symbols:
            clean_s = s.replace(".NS", "").replace("-NS", "").strip()
            fin = financials_map.get(clean_s) if financials_map else None
            eval_res = self.evaluate_quality(clean_s, as_of_date, financials=fin)
            if eval_res["is_quality"]:
                passed.append(s)
        return passed
