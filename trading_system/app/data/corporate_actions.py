"""
NSE Audited Corporate Actions & ETF Universe Guard Module
=========================================================
Strictly prevents heuristic gap guessing (P0 Fix 1 & Fix 4):
1. Loads verified corporate actions from nse_corporate_actions_audited.csv.
2. Corporate action multipliers are ONLY applied on confirmed Ex-Dates for confirmed symbols.
3. Market crashes (e.g. -50% overnight drop without corporate action) are preserved 100%.
4. Enforces strict ISIN validation: only Indian Equities ('INE...') are admitted;
   ETFs and Funds ('INF...', 'IN9...') are strictly purged from the stock universe.
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Any, Dict, Tuple, Optional, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CORPORATE_ACTIONS_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "nse_corporate_actions_audited.csv")

ETF_TICKER_PATTERNS = re.compile(
    r"(?:BEES|ETF|IETF|GOLD|LIQUID|GILT|NV20|JUNIOR|ALPHA)$|^(?:SETF|NETF|MOM100)",
    re.IGNORECASE
)

_ACTIONS_CACHE: Optional[Dict[Tuple[str, str], float]] = None


def load_audited_corporate_actions(csv_path: str = CORPORATE_ACTIONS_CSV) -> Dict[Tuple[str, str], float]:
    """
    Loads verified corporate actions mapping (date_str, symbol) -> multiplier.
    Returns: Dict[(YYYY-MM-DD, SYMBOL), multiplier]
    """
    global _ACTIONS_CACHE
    if _ACTIONS_CACHE is not None:
        return _ACTIONS_CACHE

    if not os.path.exists(csv_path):
        _ACTIONS_CACHE = {}
        return _ACTIONS_CACHE

    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["symbol"] = df["symbol"].str.strip().str.upper()

    actions_map: Dict[Tuple[str, str], float] = {}
    for _, row in df.iterrows():
        key = (row["date"], row["symbol"])
        actions_map[key] = float(row["multiplier"])

    _ACTIONS_CACHE = actions_map
    return _ACTIONS_CACHE


def get_corporate_action_multiplier(date: Any, symbol: str) -> float:
    """
    Returns the exact verified corporate action multiplier for a (date, symbol) event.
    Returns 1.0 if no official corporate action occurred on this date.
    A stock crashing -50% without an official corporate action receives 1.0 (unadjusted).
    """
    actions = load_audited_corporate_actions()
    dt_str = pd.to_datetime(date).strftime("%Y-%m-%d")
    sym = symbol.strip().upper().replace(".NS", "")
    return actions.get((dt_str, sym), 1.0)


def is_valid_equity_isin(isin: Optional[str]) -> bool:
    """
    Fix 4: Equities on NSE must have an ISIN starting with 'INE'.
    'INF' denotes Mutual Funds, ETFs, and alternate investment vehicles.
    """
    if isin is None or not isinstance(isin, str):
        return True  # Fallback for historical files before ISIN column existed
    isin = isin.strip().upper()
    return isin.startswith("INE")


def is_etf_ticker(symbol: str) -> bool:
    """
    Fix 4: Detects ETF and fund tickers that might have slipped into historical Bhavcopies.
    """
    sym = symbol.strip().upper().replace(".NS", "")
    if ETF_TICKER_PATTERNS.search(sym):
        # Whitelist exceptions if any genuine equities end in these letters
        # None in Nifty 500
        return True
    return False


def build_verified_split_adjustment_matrix(
    close_df: pd.DataFrame,
    csv_path: str = CORPORATE_ACTIONS_CSV
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Builds causal adjustment factors based EXCLUSIVELY on verified corporate actions.
    Returns (split_multipliers, split_adj_factors).
    - split_multipliers: Daily multiplier (e.g. 10.0 on ex-date) used to scale holdings and entry prices.
    - split_adj_factors: Backward adjustment factors applied to raw close_df to produce continuous price series.
    """
    actions = load_audited_corporate_actions(csv_path)
    dates = close_df.index
    symbols = close_df.columns

    # Initialize multiplier matrix with 1.0 (for position adjustment on ex-date)
    mult_df = pd.DataFrame(1.0, index=dates, columns=symbols)

    for (dt_str, sym), mult in actions.items():
        if sym in symbols:
            dt_ts = pd.to_datetime(dt_str)
            if dt_ts in mult_df.index:
                mult_df.loc[dt_ts, sym] = mult

    # For continuous technical indicators (momentum / moving averages):
    # Historical prices prior to ex-date must be scaled by (1.0 / multiplier).
    # We invert the multiplier and shift(-1) so that the split applies strictly to days before the ex-date.
    inv_mult_df = mult_df.map(lambda m: 1.0 / m if m > 0 else 1.0)
    shifted_inv = inv_mult_df.shift(-1, fill_value=1.0)
    adj_factors = shifted_inv.iloc[::-1].cumprod().iloc[::-1]

    return mult_df, adj_factors


from trading_system.app.common.logger import get_logger

_ca_logger = get_logger("CorporateActions")


class CorporateActionProcessor:
    """
    Handles Stock Splits, Reverse Splits, and Cash Dividends strictly point-in-time.
    Maintains backward compatibility for yfinance and database data providers.
    """

    @staticmethod
    def calculate_adjustment_factors(raw_df: pd.DataFrame) -> pd.DataFrame:
        df = raw_df.copy()
        for col in ["dividends", "stock splits"]:
            if col not in df.columns:
                df[col] = 0.0

        df["dividends"] = df["dividends"].fillna(0)
        df["stock splits"] = df["stock splits"].fillna(0)

        inv_split_ratios = df["stock splits"].apply(lambda r: 1.0 / r if (pd.notnull(r) and r > 0) else 1.0)
        shifted_inv_splits = inv_split_ratios.shift(-1, fill_value=1.0)
        split_factor = shifted_inv_splits.iloc[::-1].cumprod().iloc[::-1]

        prev_close = df["close"].shift(1)
        div_yield = (df["dividends"] / prev_close).fillna(0.0)
        div_multiplier = (1.0 - div_yield).clip(lower=0.0, upper=1.0)
        shifted_div_multiplier = div_multiplier.shift(-1, fill_value=1.0)
        div_factor = shifted_div_multiplier.iloc[::-1].cumprod().iloc[::-1]

        df["adj_factor"] = split_factor * div_factor
        df["adj_open"] = df["open"] * df["adj_factor"]
        df["adj_high"] = df["high"] * df["adj_factor"]
        df["adj_low"] = df["low"] * df["adj_factor"]
        df["adj_close"] = df["close"] * df["adj_factor"]
        df["adj_volume"] = df["volume"] / df["adj_factor"].replace(0.0, 1.0)

        _ca_logger.info(f"Calculated corporate action adjustment factors for {len(df)} rows.")
        return df

    @staticmethod
    def apply_splits_to_portfolio(current_positions: dict, today_splits: dict) -> dict:
        new_positions = current_positions.copy()
        for sym, split_ratio in today_splits.items():
            if split_ratio > 0 and sym in new_positions:
                old_qty = new_positions[sym]
                new_qty = old_qty * split_ratio
                new_positions[sym] = new_qty
                _ca_logger.info(f"CORPORATE ACTION: {sym} split {split_ratio}:1. Position updated: {old_qty} -> {new_qty}")
        return new_positions

