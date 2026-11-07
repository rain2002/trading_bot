"""
Production Institutional 19-Year Backtester for NSE Nifty 50 Universe (2007 - 2025)
==================================================================================
Audited Pre-Registered Dual-Pod Fiduciary Engine:
  1. Pre-Registered Variants : 1 (Wide Stops), 2 (Medium Stops), 3 (Tight Current Stops)
  2. Double High-Water Mark  : hwm_true (never resets, determines strategy MaxDD) vs hwm_ladder (operating reference)
  3. Drawdown Ladder Tiers   : -10% (70%), -18% (40%), -24% (0% Cash Defense)
  4. Recovery State Machine  : 15-day cool-off + 10-day benchmark > 200-SMA confirmation + staged ramp
  5. Sourced DP Fee          : Flat Rs 14.75 per sale scrip (Dhan schedule: Rs 12.50 + 18% GST)
  6. Holding-Period Tax      : STCG (< 365d: 15%/20%) vs LTCG (>= 365d: 0%/10%/12.5%)
  7. Point-in-Time Filter    : Strict Nifty 50 Constituent Inclusion Dates (Zero Survivorship/Lookahead)
  8. Execution Timing        : Next-Day 09:15 IST Market Open (Default)
  9. Cash Compounding        : Sourced Liquid ETF Net Yield (india_cash_yield_history.csv)
  10. Protocol Integrity     : Verifies SHA-256 hash of PRE_REGISTERED_DUAL_POD_PROTOCOL.md at startup
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import math
import glob
import json
import hashlib
import argparse
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial
from trading_system.app.data.constituent_manager import PointInTimeConstituentManager

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nse")
NIFTY_CHANGES_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_historical_components_changes.csv")
NIFTY_START_END_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "nifty50_ticker_start_end.csv")
INDIA_CASH_YIELD_CSV = os.path.join(PROJECT_ROOT, "trading_system", "data", "india_cash_yield_history.csv")
PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "PRE_REGISTERED_DUAL_POD_PROTOCOL.md")
LOCKED_PROTOCOL_SHA256 = "6B68F701474F023E62DF59B911092F2BB40E69F0F0B370B97754AFEFEAE95EDF"

# Global Institutional PIT Constituent Manager for Nifty 50
PIT_MANAGER = PointInTimeConstituentManager(
    changes_csv_path=NIFTY_CHANGES_CSV,
    start_end_csv_path=NIFTY_START_END_CSV
)

START_DATE = "2007-09-17"
DEFAULT_END_DATE = "2024-12-31"
HOLDOUT_END_DATE = "2025-12-30"

# FROZEN PARAMETERS (Strict anti-overfitting protocol)
FROZEN_KELLY_FRACTION = 0.40      # Frozen half-Kelly dampener (40% f*)
FROZEN_MOM_LOOKBACK = 90          # Frozen 90-day exponential regression window
FROZEN_MIN_ALLOC = 0.05           # 5% lower bound
FROZEN_MAX_ALLOC = 0.15           # 15% upper bound

INITIAL_CAPITAL = 80000.0         # INR (~$1,000 USD at ~80 INR/USD)
FLAT_DP_FEE_RUPEES = 14.75       # Sourced: Dhan Schedule (Rs 12.50 flat + 18% GST)
DEFAULT_SLIPPAGE_BPS = 5.0        # 5 bps institutional baseline
STRESSED_SLIPPAGE_BPS = 7.5       # 7.5 bps stressed baseline
MAX_CORE_POSITIONS = 10           # 10 High-Conviction Core Slots

# Stocks that were NEVER in Nifty 50 (or purely midcaps/recent high-flyers)
NON_NIFTY_MIDCAPS: Set[str] = {
    "DIXON.NS", "PERSISTENT.NS", "TVSMOTOR.NS", "RECLTD.NS", "PFC.NS",
    "POLYCAB.NS", "MPHASIS.NS", "SUPREMEIND.NS", "VOLTAS.NS", "NAUKRI.NS",
    "IRCTC.NS", "HAL.NS", "RVNL.NS", "CUMMINSIND.NS", "HAVELLS.NS",
    "PIDILITIND.NS", "BERGEPAINT.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
    "FEDERALBNK.NS", "CANBK.NS", "OFSS.NS", "TORNTPOWER.NS", "MAXHEALTH.NS",
    "SRF.NS", "PAGEIND.NS", "BOSCHLTD.NS", "MOTHERSON.NS", "COLPAL.NS",
    "GODREJCP.NS", "DABUR.NS", "MARICO.NS", "UNITDSPR.NS"
}

# Historical Nifty 50 Reconstitution Inclusion Dates (Symbol -> Date joined Nifty 50)
NIFTY_ADDITION_DATES: Dict[str, str] = {
    "ADANIENT.NS": "2022-09-30",
    "TRENT.NS": "2024-09-27",
    "BEL.NS": "2024-09-27",
    "SHRIRAMFIN.NS": "2024-03-28",
    "APOLLOHOSP.NS": "2022-03-31",
    "DIVISLAB.NS": "2020-09-25",
    "SBILIFE.NS": "2020-09-25",
    "HDFCLIFE.NS": "2020-03-27",
    "SHREECEM.NS": "2020-03-27",
    "TATACONSUM.NS": "2021-03-31",
    "NESTLEIND.NS": "2019-09-27",
    "BRITANNIA.NS": "2019-03-29",
    "JSWSTEEL.NS": "2018-09-28",
    "BAJAJFINSV.NS": "2018-04-02",
    "TITAN.NS": "2018-04-02",
    "BAJFINANCE.NS": "2017-09-29",
    "EICHERMOT.NS": "2016-04-01",
    "AUROPHARMA.NS": "2016-04-01",
    "ADANIPORTS.NS": "2015-09-28",
    "TECHM.NS": "2014-03-28",
    "INDUSINDBK.NS": "2013-04-01",
    "ULTRACEMCO.NS": "2012-09-28",
    "COALINDIA.NS": "2011-04-01"
}

# All-In Variable Costs (Brokerage + STT + Turnover + Stamp + GST + Slippage)
BUY_COST_BPS_NORMAL = 22.85
BUY_COST_BPS_STRESSED = 25.35
SELL_COST_BPS_NORMAL = 21.35
SELL_COST_BPS_STRESSED = 23.85


def verify_protocol_lock():
    """Verify cryptographic integrity of pre-registered protocol before execution."""
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"CRITICAL: Protocol specification file missing: {PROTOCOL_PATH}")
    with open(PROTOCOL_PATH, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest().upper()
    if sha != LOCKED_PROTOCOL_SHA256:
        raise ValueError(
            f"PRE-REGISTRATION INTEGRITY VIOLATION:\n"
            f"Protocol hash mismatch!\n"
            f"  Expected : {LOCKED_PROTOCOL_SHA256}\n"
            f"  Computed : {sha}\n"
            f"Any modification to PRE_REGISTERED_DUAL_POD_PROTOCOL.md invalidates pre-registration."
        )
    print(f"[OK] Pre-Registration Protocol v3.1 verified (SHA-256: {sha[:16]}...).")


def normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df


_CASH_YIELD_CACHE = None


def _get_cash_yield_arrays():
    global _CASH_YIELD_CACHE
    if _CASH_YIELD_CACHE is None:
        if os.path.exists(INDIA_CASH_YIELD_CSV):
            df = pd.read_csv(INDIA_CASH_YIELD_CSV)
            dates = pd.to_datetime(df["effective_date"]).values
            repo = df["rbi_repo_rate"].astype(float).values
            liquid = df["liquid_etf_net_yield"].astype(float).values
            _CASH_YIELD_CACHE = (dates, repo, liquid)
        else:
            _CASH_YIELD_CACHE = (np.array([]), np.array([]), np.array([]))
    return _CASH_YIELD_CACHE


def get_india_rf_rate(date: pd.Timestamp) -> float:
    dates, repo, _ = _get_cash_yield_arrays()
    if len(dates) == 0:
        return 0.065
    dt_val = np.datetime64(pd.to_datetime(date).strftime("%Y-%m-%d"))
    idx = np.searchsorted(dates, dt_val, side="right") - 1
    if idx < 0:
        return float(repo[0])
    return float(repo[idx])


def get_liquid_etf_yield(date: pd.Timestamp) -> float:
    dates, _, liquid = _get_cash_yield_arrays()
    if len(dates) == 0:
        return max(0.0, get_india_rf_rate(date) - 0.0065)
    dt_val = np.datetime64(pd.to_datetime(date).strftime("%Y-%m-%d"))
    idx = np.searchsorted(dates, dt_val, side="right") - 1
    if idx < 0:
        return float(liquid[0])
    return float(liquid[idx])


def compute_capital_gains_tax(entry_date, exit_date, gain: float) -> float:
    if gain <= 0.0:
        return 0.0
    holding_days = (pd.to_datetime(exit_date) - pd.to_datetime(entry_date)).days
    exit_dt = pd.to_datetime(exit_date)
    budget_2024_dt = pd.to_datetime("2024-07-23")
    ltcg_start_dt = pd.to_datetime("2018-04-01")

    if holding_days < 365:
        # STCG
        rate = 0.20 if exit_dt >= budget_2024_dt else 0.15
        return gain * rate
    else:
        # LTCG
        if exit_dt < ltcg_start_dt:
            return 0.0  # Exempt under Section 10(38)
        rate = 0.125 if exit_dt >= budget_2024_dt else 0.10
        return gain * rate


def calc_vectorized_momentum(series: np.ndarray, window: int = 90) -> np.ndarray:
    n = len(series)
    scores = np.full(n, np.nan)
    if n < window:
        return scores
    log_p = np.log(np.maximum(series, 1e-4))
    w = np.arange(window) - (window - 1.0) / 2.0
    ss_x = np.sum(w ** 2)
    w_norm = w / ss_x
    slopes = np.convolve(log_p, w_norm[::-1], mode="valid")
    s = pd.Series(log_p)
    rolling_var = s.rolling(window).var().values[window - 1:] * (window - 1)
    r2 = np.clip((slopes ** 2 * ss_x) / np.maximum(rolling_var, 1e-6), 0.0, 1.0)
    annualized_slope = np.expm1(np.clip(slopes * 252.0, -10.0, 10.0))
    scores[window - 1:] = annualized_slope * r2
    return scores


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 20) -> np.ndarray:
    n = len(close)
    if n < window + 1:
        return np.full(n, np.nan)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    s_tr = pd.Series(tr)
    return s_tr.rolling(window, min_periods=window).mean().values


def load_market_data(start_date: str = START_DATE, end_date: str = DEFAULT_END_DATE) -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any], list]:
    print(f"[1/3] Loading Official Nifty 50 Benchmark (^NSEI) Series ({start_date} to {end_date})...", flush=True)
    nsei_raw = normalize_index(pd.read_parquet(os.path.join(CACHE_DIR, "INDEX_NSEI.parquet")))
    bench_df = nsei_raw.loc[start_date:end_date].copy()
    bench_df = bench_df[~bench_df.index.duplicated(keep="last")]

    tri_daily_ret = bench_df["close"].pct_change().fillna(0.0) + (0.0135 / 252.0)
    bench_df["tri_close"] = bench_df["close"].iloc[0] * (1.0 + tri_daily_ret).cumprod()

    bench_close = bench_df["close"]
    bench_df["sma200"] = bench_close.rolling(200, min_periods=50).mean()
    bench_df["sma50"] = bench_close.rolling(50, min_periods=20).mean()

    # Routine Regime Filter:
    # Exit on 1 close below 200-SMA, re-enter on 2 consecutive closes above 200-SMA
    above_200 = (bench_close > bench_df["sma200"]).astype(int)
    macro_bull = (above_200.rolling(2, min_periods=2).sum() == 2)

    print(f"  Official Nifty 50 benchmark loaded: {len(bench_df)} trading days ({bench_df.index[0].date()} to {bench_df.index[-1].date()})", flush=True)

    print("[2/3] Precomputing Causal Indicators & Corporate Actions for NSE Universe...", flush=True)
    t0 = time.time()
    stock_files = glob.glob(os.path.join(CACHE_DIR, "*-NS.parquet"))

    precalc = {}
    for fpath in stock_files:
        sym = os.path.basename(fpath).replace("-NS.parquet", ".NS")
        try:
            df = normalize_index(pd.read_parquet(fpath))
            if len(df) < 100:
                continue

            close = df["close"].values
            open_p = df["open"].values
            high = df["high"].values
            low = df["low"].values
            divs = df.get("dividends", pd.Series(0.0, index=df.index)).values
            splits = df.get("stock_splits", pd.Series(0.0, index=df.index)).values

            close_s = pd.Series(close, index=df.index)
            sma100 = close_s.rolling(100, min_periods=30).mean().values
            sma150 = close_s.rolling(150, min_periods=50).mean().values
            sma200 = close_s.rolling(200, min_periods=50).mean().values
            mom90 = calc_vectorized_momentum(close, window=FROZEN_MOM_LOOKBACK)
            atr20 = calc_atr(high, low, close, window=20)

            precalc[sym] = {
                "dates": df.index,
                "close": close,
                "open": open_p,
                "high": high,
                "low": low,
                "divs": divs,
                "splits": splits,
                "sma100": sma100,
                "sma150": sma150,
                "sma200": sma200,
                "mom90": mom90,
                "atr20": atr20,
                "date_to_idx": {d: idx for idx, d in enumerate(df.index)}
            }
        except Exception:
            pass

    print(f"  Precalculated causal features for {len(precalc)} NSE equities in {time.time()-t0:.2f}s.", flush=True)
    timeline = sorted(list(bench_df.index))
    print(f"[3/3] Timeline aligned: {len(timeline)} trading days from {timeline[0].date()} to {timeline[-1].date()}\n", flush=True)

    return bench_df, macro_bull, precalc, timeline


def compute_baselines(bench_df: pd.DataFrame, precalc: Dict[str, Any], timeline: list) -> Dict[str, Dict[str, Any]]:
    """Evaluates mandatory baselines over common window under identical stressed costs and post-tax accounting."""
    from trading_system.scripts.diagnose_nse_baselines import compute_metrics
    bench_sub = bench_df.loc[timeline[0]:timeline[-1]]
    dates = list(bench_sub.index)
    years = (dates[-1] - dates[0]).days / 365.25
    nsei_close = bench_sub["close"]

    # Baseline 1: Nifty 50 TRI (Post-Tax)
    b1_start_cash = INITIAL_CAPITAL * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
    b1_shares = b1_start_cash / nsei_close.iloc[0]
    b1_list = []
    for dt, p in zip(dates, nsei_close):
        b1_shares *= (1.0 + 0.0135 / 252.0)
        b1_list.append(b1_shares * p)
    b1_series = pd.Series(b1_list, index=dates)
    final_proceeds = b1_shares * nsei_close.iloc[-1] * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
    tax_b1 = compute_capital_gains_tax(dates[0], dates[-1], final_proceeds - INITIAL_CAPITAL)
    b1_series.iloc[-1] = final_proceeds - tax_b1
    m_b1 = compute_metrics(b1_series, "Baseline 1: Buy-and-Hold Nifty 50 TRI (Post-Tax)")

    # Baseline 3: Trend-Switch > 200-SMA (Post-Tax)
    sma200 = bench_sub["sma200"]
    above_200 = nsei_close > sma200
    b3_cash = INITIAL_CAPITAL
    b3_shares = 0.0
    b3_entry_cost = 0.0
    b3_entry_date = None
    b3_list = []
    b3_cash_days = 0

    for dt, close_p, is_above in zip(dates, nsei_close, above_200):
        daily_yield = get_liquid_etf_yield(dt) / 252.0
        if is_above:
            if b3_shares == 0.0 and b3_cash > 0:
                buy_net = b3_cash * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
                b3_shares = buy_net / close_p
                b3_entry_cost = b3_cash
                b3_entry_date = dt
                b3_cash = 0.0
            b3_shares *= (1.0 + 0.0135 / 252.0)
            daily_val = b3_shares * close_p
        else:
            b3_cash_days += 1
            if b3_shares > 0:
                gross = b3_shares * close_p
                net = gross * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
                gain = net - b3_entry_cost
                tax = compute_capital_gains_tax(b3_entry_date, dt, gain)
                b3_cash = net - tax
                b3_shares = 0.0
                b3_entry_date = None
            b3_cash *= (1.0 + daily_yield)
            daily_val = b3_cash
        b3_list.append(daily_val)
    b3_series = pd.Series(b3_list, index=dates)
    m_b3 = compute_metrics(b3_series, "Baseline 3: Trend-Switch > 200-SMA (Post-Tax)")
    m_b3["days_in_cash_pct"] = round((b3_cash_days / len(dates)) * 100.0, 1)

    # Baseline 2: Equal-Weight PIT Nifty 50 (Post-Tax)
    years_list = sorted(list(set(d.year for d in dates)))
    ew_list = []
    ew_cash = INITIAL_CAPITAL
    ew_pos = {}
    for yr in years_list:
        yr_dates = [d for d in dates if d.year == yr]
        if not yr_dates:
            continue
        first_day = yr_dates[0]
        eligible = [
            s for s, p in precalc.items()
            if PIT_MANAGER.is_constituent(s, first_day) and first_day in p["date_to_idx"] and p["close"][p["date_to_idx"][first_day]] > 0
        ]
        if ew_pos:
            for s, pos in list(ew_pos.items()):
                p = precalc[s]["close"][precalc[s]["date_to_idx"][first_day]] if first_day in precalc[s]["date_to_idx"] else pos["entry_price"]
                gross = pos["shares"] * p
                net = gross * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
                gain = net - (pos["shares"] * pos["entry_price"])
                tax = compute_capital_gains_tax(pos["entry_date"], first_day, gain)
                ew_cash += (net - tax)
            ew_pos = {}
        if eligible and ew_cash > 0:
            alloc = ew_cash / len(eligible)
            for s in eligible:
                p = precalc[s]["close"][precalc[s]["date_to_idx"][first_day]]
                net_alloc = alloc * (1.0 - BUY_COST_BPS_STRESSED / 10000.0)
                ew_pos[s] = {"shares": net_alloc / p, "entry_price": p, "entry_date": first_day}
            ew_cash = 0.0
        for d in yr_dates:
            active_today = PIT_MANAGER.get_active_constituents(d)
            for s in list(ew_pos.keys()):
                if PointInTimeConstituentManager.normalize_symbol(s) not in active_today:
                    pos = ew_pos.pop(s)
                    p = precalc[s]["close"][precalc[s]["date_to_idx"][d]] if d in precalc[s]["date_to_idx"] else pos["entry_price"]
                    gross = pos["shares"] * p
                    net = gross * (1.0 - SELL_COST_BPS_STRESSED / 10000.0) - FLAT_DP_FEE_RUPEES
                    gain = net - (pos["shares"] * pos["entry_price"])
                    tax = compute_capital_gains_tax(pos["entry_date"], d, gain)
                    ew_cash += (net - tax)
            val = ew_cash + sum(pos["shares"] * precalc[s]["close"][precalc[s]["date_to_idx"][d]] for s, pos in ew_pos.items() if d in precalc[s]["date_to_idx"])
            ew_list.append(val)
    ew_series = pd.Series(ew_list, index=dates[:len(ew_list)])
    m_b2 = compute_metrics(ew_series, "Baseline 2: Equal-Weight PIT Nifty 50 (Post-Tax)")

    m_b1["terminal_equity"] = m_b1["end_val"]
    m_b2["terminal_equity"] = m_b2["end_val"]
    m_b3["terminal_equity"] = m_b3["end_val"]

    return {
        "baseline_1_tri": m_b1,
        "baseline_2_equal_weight": m_b2,
        "baseline_3_trend_cash": m_b3
    }


def run_simulation(
    bench_df: pd.DataFrame,
    macro_bull: pd.Series,
    precalc: Dict[str, Any],
    timeline: list,
    variant: int = 1,
    slippage_bps: float = 5.0,
    strict_pit: bool = True,
    cash_mode: str = "LIQUID_BEES",
    execution_fill: str = "NEXT_OPEN",
    use_vol_parity: bool = False,
    label: str = "Variant 1 (Wide Stops)"
) -> Dict[str, Any]:
    print(f">>> Running Simulation [{label}] (Variant {variant}, Slippage: {slippage_bps:.2f} bps, Fill: {execution_fill})...", flush=True)
    t_start = time.time()

    # Pre-registered Stop & Exit Parameters per Variant
    if variant == 1:
        hard_stop_pct = -0.15
        win_prov_gain = 0.40
        win_prov_trail = -0.20
        win_mod_gain = 0.20
        win_mod_trail = -0.15
        trend_sma_key = "sma200"
    elif variant == 2:
        hard_stop_pct = -0.10
        win_prov_gain = 0.35
        win_prov_trail = -0.15
        win_mod_gain = 0.18
        win_mod_trail = -0.10
        trend_sma_key = "sma100"
    else:  # Variant 3: Tight
        hard_stop_pct = -0.08
        win_prov_gain = 0.30
        win_prov_trail = -0.12
        win_mod_gain = 0.15
        win_mod_trail = -0.08
        trend_sma_key = "sma100"

    cash = INITIAL_CAPITAL
    positions: Dict[str, float] = {}          # sym -> shares
    entry_prices: Dict[str, float] = {}       # sym -> entry price
    entry_dates: Dict[str, pd.Timestamp] = {} # sym -> entry date
    peak_prices: Dict[str, float] = {}        # sym -> peak price

    # Double High-Water Mark Invariant
    hwm_true = INITIAL_CAPITAL                # Lifetime never-reset peak
    hwm_ladder = INITIAL_CAPITAL              # Operating ladder reference
    max_true_drawdown = 0.0
    hard_breach_detected = False

    # Emergency Tier 4 Recovery State Machine
    in_tier4_defense = False
    cooling_off_counter = 0
    recovery_streak = 0
    recovery_stage = 0
    recovery_stage_days = 0

    trade_log = []
    equity_curve = {}
    cash_curve = {}
    stock_curve = {}
    total_divs = 0.0
    total_interest = 0.0
    total_dp_fees = 0.0
    total_tax_paid = 0.0
    splits_count = 0
    pending_buys = []

    buy_fee_rate = (BUY_COST_BPS_STRESSED if slippage_bps > 5.0 else BUY_COST_BPS_NORMAL) / 10000.0
    sell_fee_rate = (SELL_COST_BPS_STRESSED if slippage_bps > 5.0 else SELL_COST_BPS_NORMAL) / 10000.0

    for day_idx, current_date in enumerate(timeline):
        is_routine_bull = bool(macro_bull.loc[current_date]) if current_date in macro_bull.index else True
        is_rebalance_day = (day_idx % 5 == 0)

        # Step 0: Execute Pending Orders at TODAY'S OPEN
        if execution_fill == "NEXT_OPEN" and pending_buys:
            for p_order in pending_buys:
                sym = p_order["symbol"]
                target_alloc = p_order["target_alloc"]
                score = p_order["score"]
                kelly_alloc = p_order["kelly_alloc"]

                if sym not in precalc or current_date not in precalc[sym]["date_to_idx"]:
                    continue
                idx = precalc[sym]["date_to_idx"][current_date]
                open_price = precalc[sym]["open"][idx]
                if open_price <= 0 or math.isnan(open_price):
                    continue

                fill_price = open_price * (1.0 + buy_fee_rate)
                alloc = min(target_alloc, cash * 0.96)

                if alloc >= 500.0:
                    shares = round(alloc / fill_price, 4)
                    cost = shares * fill_price
                    if cost <= cash and shares > 0:
                        cash -= cost
                        positions[sym] = shares
                        entry_prices[sym] = fill_price
                        entry_dates[sym] = current_date
                        peak_prices[sym] = open_price

                        trade_log.append({
                            "date": current_date,
                            "symbol": sym,
                            "action": "BUY",
                            "shares": shares,
                            "price": fill_price,
                            "cost": cost,
                            "reason": f"ENTRY Score: {score:.2f} | Kelly: {kelly_alloc*100:.1f}%"
                        })
            pending_buys = []

        # Step A: Daily Cash Compounding (Liquid ETF Net Yield)
        daily_interest = 0.0
        if cash_mode == "LIQUID_BEES":
            daily_interest = cash * (get_liquid_etf_yield(current_date) / 252.0)
        elif cash_mode == "T_BILLS":
            daily_interest = cash * (get_india_rf_rate(current_date) / 252.0)
        cash += daily_interest
        total_interest += daily_interest

        # Step B: Mark-to-Market
        current_prices = {}
        for sym, shares in list(positions.items()):
            if sym not in precalc:
                continue
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                current_prices[sym] = price

                # Cash Dividends
                div_per_share = p_sym["divs"][idx]
                if div_per_share > 0:
                    div_amount = shares * div_per_share
                    cash += div_amount
                    total_divs += div_amount

                # Stock Splits
                split_ratio = p_sym["splits"][idx]
                if split_ratio > 0 and split_ratio != 1.0:
                    positions[sym] = shares * split_ratio
                    entry_prices[sym] = entry_prices[sym] / split_ratio
                    splits_count += 1

                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        total_equity = cash + portfolio_equity

        # Step C: Double High-Water Mark Evaluation
        # 1. Lifetime never-reset peak (hwm_true)
        if total_equity > hwm_true:
            hwm_true = total_equity
        true_dd = (total_equity - hwm_true) / hwm_true
        if true_dd < max_true_drawdown:
            max_true_drawdown = true_dd
        if true_dd < -0.3000:
            hard_breach_detected = True

        # 2. Operating ladder reference (hwm_ladder)
        if not in_tier4_defense:
            if total_equity > hwm_ladder:
                hwm_ladder = total_equity
        operating_dd = (total_equity - hwm_ladder) / hwm_ladder

        # Step D: Drawdown Ladder & Recovery State Machine
        bench_close_today = bench_df.loc[current_date, "close"] if current_date in bench_df.index else 0.0
        bench_sma200_today = bench_df.loc[current_date, "sma200"] if current_date in bench_df.index else 0.0
        bench_sma50_today = bench_df.loc[current_date, "sma50"] if current_date in bench_df.index else 0.0

        sma50_sloping_up = True
        if current_date in bench_df.index:
            b_idx = bench_df.index.get_loc(current_date)
            if b_idx >= 5:
                sma50_sloping_up = bench_sma50_today > bench_df["sma50"].iloc[b_idx - 5]

        is_macro_bull_regime = (bench_close_today > bench_sma200_today) and sma50_sloping_up

        if in_tier4_defense:
            cooling_off_counter += 1
            if is_macro_bull_regime and cooling_off_counter >= 15:
                recovery_streak += 1
            else:
                recovery_streak = 0

            if cooling_off_counter >= 15 and recovery_streak >= 10:
                # Emergency recovery unlocked! Re-anchor operating ladder
                in_tier4_defense = False
                hwm_ladder = total_equity
                recovery_stage = 1
                recovery_stage_days = 0
                allowed_exposure = 0.40
            else:
                allowed_exposure = 0.0
        else:
            if recovery_stage == 1:
                allowed_exposure = 0.40
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 2
                    recovery_stage_days = 0
            elif recovery_stage == 2:
                allowed_exposure = 0.70
                recovery_stage_days += 1
                if recovery_stage_days >= 10:
                    recovery_stage = 3
                    recovery_stage_days = 0
            elif recovery_stage == 3:
                allowed_exposure = 1.00
                recovery_stage = 0
            else:
                if operating_dd >= -0.10:
                    allowed_exposure = 1.00
                elif operating_dd >= -0.18:
                    allowed_exposure = 0.70
                elif operating_dd >= -0.24:
                    allowed_exposure = 0.40
                else:
                    # Breached -24% -> Trigger Tier 4 Emergency Defense
                    in_tier4_defense = True
                    cooling_off_counter = 0
                    recovery_streak = 0
                    recovery_stage = 0
                    allowed_exposure = 0.0

        # Precedence Rule: If in Tier 4 Cash Defense, allowed_exposure = 0.0 overrides routine filter.
        # Otherwise, if routine regime filter triggers (close < 200-SMA), reduce allowed_exposure to 0.0.
        effective_exposure_cap = allowed_exposure if is_routine_bull else 0.0

        # Step E: Exit Evaluations
        liquidations = []
        active_today = PIT_MANAGER.get_active_constituents(current_date) if strict_pit else set()

        if effective_exposure_cap == 0.0:
            # Full liquidation to cash
            for sym in list(positions.keys()):
                reason = "TIER4_CASH_DEFENSE" if in_tier4_defense else "MACRO_BEAR_CASH_GATE"
                liquidations.append((sym, reason))
        else:
            for sym, shares in list(positions.items()):
                # Drop stock immediately on removal from Nifty 50 index
                if strict_pit and PointInTimeConstituentManager.normalize_symbol(sym) not in active_today:
                    liquidations.append((sym, "NIFTY50_CONSTITUENT_REMOVAL"))
                    continue

                if sym not in current_prices or sym not in precalc:
                    liquidations.append((sym, "DATA_HALT_LIQUIDATE"))
                    continue

                price = current_prices[sym]
                cost = entry_prices.get(sym, price)
                plpc = (price - cost) / cost if cost > 0 else 0.0
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]
                peak = peak_prices.get(sym, price)
                pullback = (price - peak) / peak if peak > 0 else 0.0

                # 1. Hard Stop-Loss
                if plpc <= hard_stop_pct:
                    liquidations.append((sym, f"HARD_STOP ({hard_stop_pct*100:.1f}%) [Loss: {plpc*100:.1f}%]"))
                    continue

                # 2. Proven Winner Trailing Stop
                if plpc >= win_prov_gain:
                    if pullback <= win_prov_trail:
                        liquidations.append((sym, f"WINNER_TRAIL_PROV [PnL: {plpc*100:+.1f}%, Pullback: {pullback*100:.1f}%]"))
                        continue
                # 3. Moderate Winner Trailing Stop
                elif plpc >= win_mod_gain:
                    if pullback <= win_mod_trail:
                        liquidations.append((sym, f"WINNER_TRAIL_MOD [PnL: {plpc*100:+.1f}%, Pullback: {pullback*100:.1f}%]"))
                        continue
                # 4. Developing Trend Exit
                else:
                    sma_val = p_sym[trend_sma_key][idx]
                    if not math.isnan(sma_val) and price < sma_val:
                        liquidations.append((sym, f"TREND_{trend_sma_key.upper()}_BREAK [PnL: {plpc*100:+.1f}%]"))
                        continue

        # Execute liquidations
        for sym, reason in liquidations:
            shares = positions[sym]
            price = current_prices.get(sym, entry_prices.get(sym, 0.0))
            fill_price = price * (1.0 - sell_fee_rate)
            proceeds = shares * fill_price

            # Deduct flat DP fee per sale
            cash += (proceeds - FLAT_DP_FEE_RUPEES)
            total_dp_fees += FLAT_DP_FEE_RUPEES

            cost = entry_prices.get(sym, price)
            gain = proceeds - (shares * cost) - FLAT_DP_FEE_RUPEES
            entry_dt = entry_dates.get(sym, current_date)
            tax = compute_capital_gains_tax(entry_dt, current_date, gain)
            cash -= tax
            total_tax_paid += tax

            trade_log.append({
                "date": current_date,
                "symbol": sym,
                "action": "SELL",
                "shares": shares,
                "price": fill_price,
                "realized_pnl": gain,
                "pnl_pct": (fill_price - cost) / cost if cost > 0 else 0.0,
                "dp_fee": FLAT_DP_FEE_RUPEES,
                "tax": tax,
                "reason": reason
            })
            del positions[sym]
            entry_prices.pop(sym, None)
            entry_dates.pop(sym, None)
            peak_prices.pop(sym, None)

        # Step F: Entries with Causal Kelly Sizing & Zero-Leverage Ladder Cap
        if effective_exposure_cap > 0.0 and is_rebalance_day and len(positions) < MAX_CORE_POSITIONS and cash > 500.0:
            open_slots = MAX_CORE_POSITIONS - len(positions)
            cands = []

            for sym, p_sym in precalc.items():
                if sym in positions:
                    continue
                if strict_pit and PointInTimeConstituentManager.normalize_symbol(sym) not in active_today:
                    continue
                if current_date not in p_sym["date_to_idx"]:
                    continue
                idx = p_sym["date_to_idx"][current_date]
                if idx < 100:
                    continue

                score = p_sym["mom90"][idx]
                price = p_sym["close"][idx]
                sma_trend = p_sym[trend_sma_key][idx]
                atr = p_sym["atr20"][idx]

                if not math.isnan(score) and score > 0.15 and not math.isnan(sma_trend) and price > sma_trend:
                    cands.append({"symbol": sym, "price": price, "score": score, "atr": atr})

            cands.sort(key=lambda x: x["score"], reverse=True)

            # Causal Kelly Sizing
            past_closed = [t for t in trade_log if t["action"] == "SELL"]
            if len(past_closed) >= 20:
                recent = past_closed[-50:]
                wins = [t["pnl_pct"] for t in recent if t["pnl_pct"] > 0]
                losses = [abs(t["pnl_pct"]) for t in recent if t["pnl_pct"] < 0]
                p_win = len(wins) / len(recent) if recent else 0.42
                avg_w = np.mean(wins) if wins else 0.18
                avg_l = np.mean(losses) if losses else 0.07
                b_ratio = avg_w / avg_l if avg_l > 0 else 2.5
                f_star = p_win - (1.0 - p_win) / b_ratio
                kelly_alloc = float(np.clip(FROZEN_KELLY_FRACTION * f_star, FROZEN_MIN_ALLOC, FROZEN_MAX_ALLOC))
            else:
                kelly_alloc = 1.0 / MAX_CORE_POSITIONS

            # Zero-Leverage Portfolio Exposure Constraint
            max_allowed_portfolio_capital = total_equity * effective_exposure_cap
            current_allocated = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
            budget_for_entries = max(0.0, min(cash * 0.96, max_allowed_portfolio_capital - current_allocated))

            selected_cands = cands[:open_slots]
            if selected_cands and budget_for_entries > 500.0:
                alloc_per_cand = min(total_equity * kelly_alloc, budget_for_entries / len(selected_cands))

                for cand in selected_cands:
                    if budget_for_entries < 500.0:
                        break
                    sym = cand["symbol"]
                    price = cand["price"]
                    alloc = min(alloc_per_cand, budget_for_entries)

                    if execution_fill == "CLOSE":
                        fill_price = price * (1.0 + buy_fee_rate)
                        if alloc >= 500.0:
                            shares = round(alloc / fill_price, 4)
                            cost = shares * fill_price
                            if cost <= cash and shares > 0:
                                cash -= cost
                                budget_for_entries -= cost
                                positions[sym] = shares
                                entry_prices[sym] = fill_price
                                entry_dates[sym] = current_date
                                peak_prices[sym] = price
                                current_prices[sym] = price

                                trade_log.append({
                                    "date": current_date,
                                    "symbol": sym,
                                    "action": "BUY",
                                    "shares": shares,
                                    "price": fill_price,
                                    "cost": cost,
                                    "reason": f"ENTRY Score: {cand['score']:.2f} | Kelly: {kelly_alloc*100:.1f}%"
                                })
                    elif execution_fill == "NEXT_OPEN":
                        pending_buys.append({
                            "symbol": sym, "target_alloc": alloc,
                            "score": cand["score"], "kelly_alloc": kelly_alloc
                        })
                        budget_for_entries -= alloc

        # STRICT FIDUCIARY CHECK: Share count strictly >= 0
        for sym, shares in positions.items():
            if shares < 0:
                raise ValueError(f"CRITICAL FIDUCIARY BREACH: Negative share count: {sym}={shares}")

        portfolio_equity = sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        daily_equity = cash + portfolio_equity
        equity_curve[current_date] = round(daily_equity, 2)
        cash_curve[current_date] = round(cash, 2)
        stock_curve[current_date] = round(portfolio_equity, 2)

    sim_duration = time.time() - t_start
    print(f"  Simulation completed in {sim_duration:.2f}s.", flush=True)

    eq_series = pd.Series(equity_curve)
    final_eq = eq_series.iloc[-1]
    years = (pd.to_datetime(timeline[-1]) - pd.to_datetime(timeline[0])).days / 365.25
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    tot_ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0

    # True Max Drawdown calculated strictly against hwm_true (never reset)
    peak_series = eq_series.cummax()
    true_dd_series = (eq_series - peak_series) / peak_series
    max_dd = true_dd_series.min() * 100.0

    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / (ret_daily.std() + 1e-9)) * np.sqrt(252) if ret_daily.std() > 0 else 0.0
    downside_std = ret_daily[ret_daily < 0].std()
    sortino = (ret_daily.mean() / (downside_std + 1e-9)) * np.sqrt(252) if downside_std > 0 else 0.0
    calmar = abs(cagr / max_dd) if abs(max_dd) > 1e-6 else 0.0

    closed = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    gross_p = sum(t["realized_pnl"] for t in wins)
    gross_l = abs(sum(t["realized_pnl"] for t in closed if t["realized_pnl"] <= 0))
    pf = gross_p / gross_l if gross_l > 0 else 0.0

    cash_s = pd.Series(cash_curve)
    stock_s = pd.Series(stock_curve)
    days_in_cash_pct = (stock_s == 0.0).sum() / len(stock_s) * 100.0
    avg_exposure_pct = (stock_s / eq_series).mean() * 100.0

    return {
        "label": label,
        "variant": variant,
        "slippage_bps": slippage_bps,
        "starting_capital": INITIAL_CAPITAL,
        "terminal_equity": round(final_eq, 2),
        "total_return_pct": round(tot_ret, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "hard_breach_detected": hard_breach_detected,
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(pf, 2),
        "closed_trades": len(closed),
        "trades_per_year": round(len(closed) / years, 1),
        "days_in_cash_pct": round(days_in_cash_pct, 1),
        "avg_exposure_pct": round(avg_exposure_pct, 1),
        "total_dividends": round(total_divs, 2),
        "total_interest": round(total_interest, 2),
        "total_dp_fees": round(total_dp_fees, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "splits_handled": splits_count,
        "equity_curve": eq_series
    }


def print_comparative_tear_sheet(normal_res: Dict[str, Any], stressed_res: Dict[str, Any], baselines: Dict[str, Any]):
    print("\n" + "=" * 105)
    print("=" * 20 + " PRE-REGISTERED INSTITUTIONAL NSE NIFTY 50 TEAR SHEET " + "=" * 23)
    print("=" * 105)
    print(f"{'Performance Metric':<40} | {'Normal Costs':<18} | {'Stressed Costs [Gate A]':<26} | {'Baseline 3 (Trend)':<18}")
    print("-" * 105)
    b1 = baselines["baseline_1_tri"]
    b2 = baselines["baseline_2_equal_weight"]
    b3 = baselines["baseline_3_trend_cash"]

    print(f"{'Starting Capital':<40} | INR {normal_res['starting_capital']:>10,.0f}     | INR {stressed_res['starting_capital']:>18,.0f}     | INR {INITIAL_CAPITAL:>10,.0f}")
    print(f"{'Terminal Equity (Post-Tax)':<40} | INR {normal_res['terminal_equity']:>10,.0f}     | INR {stressed_res['terminal_equity']:>18,.0f}     | INR {b3['end_val']:>10,.0f}")
    print(f"{'Compound Annual Growth Rate (Post-Tax)':<40} | {normal_res['cagr_pct']:>13.2f}%    | {stressed_res['cagr_pct']:>21.2f}%    | {b3['cagr_pct']:>13.2f}%")
    print(f"{'Maximum Drawdown Depth (True HWM)':<40} | {normal_res['max_drawdown_pct']:>13.2f}%    | {stressed_res['max_drawdown_pct']:>21.2f}%    | {b3['max_drawdown_pct']:>13.2f}%")
    print(f"{'Calmar Ratio (CAGR / MaxDD)':<40} | {normal_res['calmar_ratio']:>14.2f}     | {stressed_res['calmar_ratio']:>22.2f}     | {b3['calmar_ratio']:>14.2f}")
    print(f"{'Annualized Sharpe Ratio':<40} | {normal_res['sharpe_ratio']:>14.2f}     | {stressed_res['sharpe_ratio']:>22.2f}     | {b3['sharpe_ratio']:>14.2f}")
    print(f"{'Trade Win Rate':<40} | {normal_res['win_rate_pct']:>13.2f}%    | {stressed_res['win_rate_pct']:>21.2f}%    | N/A")
    print(f"{'Profit Factor':<40} | {normal_res['profit_factor']:>14.2f}     | {stressed_res['profit_factor']:>22.2f}     | N/A")
    print(f"{'Total Closed Trades':<40} | {normal_res['closed_trades']:>14,d}     | {stressed_res['closed_trades']:>22,d}     | N/A")
    print(f"{'Days Spent 100% in Idle Cash':<40} | {normal_res['days_in_cash_pct']:>13.1f}%    | {stressed_res['days_in_cash_pct']:>21.1f}%    | {b3['days_in_cash_pct']:>13.1f}%")
    print(f"{'Average Equity Exposure':<40} | {normal_res['avg_exposure_pct']:>13.1f}%    | {stressed_res['avg_exposure_pct']:>21.1f}%    | N/A")
    print(f"{'Total DP Fees Paid (Rs 14.75/sale)':<40} | INR {normal_res['total_dp_fees']:>10,.2f}     | INR {stressed_res['total_dp_fees']:>18,.2f}     | N/A")
    print(f"{'Total Statutory Capital Gains Tax':<40} | INR {normal_res['total_tax_paid']:>10,.2f}     | INR {stressed_res['total_tax_paid']:>18,.2f}     | Included")
    print("-" * 105)
    print("                                MANDATORY BASELINE BENCHMARKS (POST-TAX)")
    print("-" * 105)
    print(f"{'Baseline 1: Buy-and-Hold Nifty 50 TRI':<40} | Post-Tax CAGR: {b1['cagr_pct']:>6.2f}% | Max DD: {b1['max_drawdown_pct']:>7.2f}% | Calmar: {b1['calmar_ratio']:>5.2f}")
    print(f"{'Baseline 2: Equal-Weight Nifty 50 (PIT)':<40} | Post-Tax CAGR: {b2['cagr_pct']:>6.2f}% | Max DD: {b2['max_drawdown_pct']:>7.2f}% | Calmar: {b2['calmar_ratio']:>5.2f}")
    print(f"{'Baseline 3: Trend-Switch > 200-SMA':<40} | Post-Tax CAGR: {b3['cagr_pct']:>6.2f}% | Max DD: {b3['max_drawdown_pct']:>7.2f}% | Calmar: {b3['calmar_ratio']:>5.2f}")
    print("=" * 105 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Pre-Registered Institutional NSE Nifty 50 Backtester")
    parser.add_argument("--variant", type=int, choices=[1, 2, 3], default=1, help="Pre-registered Variant: 1 (Wide), 2 (Medium), 3 (Tight)")
    parser.add_argument("--unconstrained", action="store_true", help="Include non-Nifty midcaps (Diagnostic only)")
    parser.add_argument("--same-bar-close", action="store_true", help="Fill orders at Day t close (Diagnostic only)")
    parser.add_argument("--zero-cash", action="store_true", help="Set cash yield to 0.0% (Diagnostic only)")
    parser.add_argument("--vol-parity", action="store_true", help="Enable Inverse-ATR Volatility Parity sizing")
    parser.add_argument("--open-holdout", action="store_true", help="Open 12-month holdout through 2025-12-30 (Caution: Burns holdout)")
    parser.add_argument("--skip-protocol-check", action="store_true", help="Skip protocol lock verification (Debugging only)")
    args = parser.parse_args()

    # Step 0: Cryptographic Protocol Lock Verification
    if not args.skip_protocol_check:
        verify_protocol_lock()

    strict_pit = not args.unconstrained
    execution_fill = "CLOSE" if args.same_bar_close else "NEXT_OPEN"
    cash_mode = "ZERO" if args.zero_cash else "LIQUID_BEES"
    end_date = HOLDOUT_END_DATE if args.open_holdout else DEFAULT_END_DATE

    bench_df, macro_bull, precalc, timeline = load_market_data(start_date=START_DATE, end_date=end_date)

    # 1. Run mandatory baselines
    print(">>> Precomputing Mandatory Baselines (TRI, Equal-Weight, Trend-Switch)...", flush=True)
    baselines = compute_baselines(bench_df, precalc, timeline)

    # 2. Run Pre-Registered Strategy Variant (Normal & Stressed Costs)
    variant_names = {1: "Wide Stops", 2: "Medium Stops", 3: "Tight Stops"}
    v_name = variant_names.get(args.variant, f"Variant {args.variant}")

    norm_label = f"Normal Costs (5.0 bps) [Variant {args.variant}: {v_name}]"
    normal_res = run_simulation(
        bench_df, macro_bull, precalc, timeline,
        variant=args.variant,
        slippage_bps=DEFAULT_SLIPPAGE_BPS,
        strict_pit=strict_pit,
        cash_mode=cash_mode,
        execution_fill=execution_fill,
        use_vol_parity=args.vol_parity,
        label=norm_label
    )

    stress_label = f"Stressed Costs (7.5 bps) [Variant {args.variant}: {v_name}] [Gate A]"
    stressed_res = run_simulation(
        bench_df, macro_bull, precalc, timeline,
        variant=args.variant,
        slippage_bps=STRESSED_SLIPPAGE_BPS,
        strict_pit=strict_pit,
        cash_mode=cash_mode,
        execution_fill=execution_fill,
        use_vol_parity=args.vol_parity,
        label=stress_label
    )

    print_comparative_tear_sheet(normal_res, stressed_res, baselines)

    b3 = baselines["baseline_3_trend_cash"]
    # Gate A Acceptance Rule:
    # 1. Post-Tax Stressed CAGR >= 15.00%
    # 2. Stressed Max Drawdown Depth <= 25.00% Target (Hard reject if > 30.00%)
    # 3. No Hard Reject Breach (> 30% from true HWM)
    # 4. Beats Baseline 3 on CAGR (> 6.58%) and Calmar (> 0.25)
    gate_a_passed = bool(
        stressed_res["cagr_pct"] >= 15.0 and
        stressed_res["max_drawdown_pct"] >= -25.0 and
        not stressed_res["hard_breach_detected"] and
        stressed_res["cagr_pct"] > b3["cagr_pct"] and
        stressed_res["calmar_ratio"] > b3["calmar_ratio"]
    )

    # Save summary json
    summary_data = {
        "protocol_sha256": LOCKED_PROTOCOL_SHA256,
        "variant": args.variant,
        "variant_name": v_name,
        "normal_run": {k: v for k, v in normal_res.items() if not isinstance(v, (pd.Series, list))},
        "stressed_run": {k: v for k, v in stressed_res.items() if not isinstance(v, (pd.Series, list))},
        "baselines": baselines,
        "gate_a_evaluated_on": "stressed_run",
        "gate_a_passed": gate_a_passed,
        "hard_breach_detected": stressed_res["hard_breach_detected"],
        "holdout_opened": bool(args.open_holdout),
        "frozen_kelly_fraction": FROZEN_KELLY_FRACTION,
        "frozen_mom_lookback": FROZEN_MOM_LOOKBACK
    }
    json_path = os.path.join(PROJECT_ROOT, "trading_system", "data", f"backtest_results_nse50_variant_{args.variant}.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(summary_data, jf, indent=2)
    print(f"[OK] NSE Variant {args.variant} results saved to: {json_path}")

    # Log to trial_log.csv
    log_trial(
        cagr_pct=normal_res["cagr_pct"],
        max_drawdown_pct=normal_res["max_drawdown_pct"],
        sharpe_ratio=normal_res["sharpe_ratio"],
        kelly_fraction=FROZEN_KELLY_FRACTION,
        lookback_days=FROZEN_MOM_LOOKBACK,
        is_holdout_opened=args.open_holdout,
        script="backtest_nse50.py",
        universe="NSE_NIFTY50",
        notes=f"Pre-Registered Variant {args.variant} ({v_name}) Normal | {'HOLDOUT_OPENED' if args.open_holdout else 'IN_SAMPLE'}"
    )
    log_trial(
        cagr_pct=stressed_res["cagr_pct"],
        max_drawdown_pct=stressed_res["max_drawdown_pct"],
        sharpe_ratio=stressed_res["sharpe_ratio"],
        kelly_fraction=FROZEN_KELLY_FRACTION,
        lookback_days=FROZEN_MOM_LOOKBACK,
        is_holdout_opened=args.open_holdout,
        script="backtest_nse50.py",
        universe="NSE_NIFTY50",
        notes=f"Pre-Registered Variant {args.variant} ({v_name}) Stressed [Gate A] | {'HOLDOUT_OPENED' if args.open_holdout else 'IN_SAMPLE'}"
    )
    print(f"[OK] Appended to trial_log.csv (Variant {args.variant}: {v_name})\n")


if __name__ == "__main__":
    main()
