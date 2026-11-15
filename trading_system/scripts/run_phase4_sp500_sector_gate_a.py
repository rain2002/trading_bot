"""
Phase 4 Gate A Simulation: S&P 500 Sector Market-Neutral Bot
============================================================
Executes the pre-registered protocol:
  - Base Protocol: PROTOCOL-SP500-SECTOR-MARKET-NEUTRAL-V1-20261114
    (SHA-256: cf3c41200397f7f87d0d3e3254de32e4083e9be5f96728d36f87bc72a8d848e7)

Candidates Evaluated (Declared Trial Family N = 3):
  - M1: 12-month total return skipping last month (12-1 momentum), ranked across sectors.
        Long Top 3 sectors (50% equity total, equal-weight); Short SPY beta-cancelled.
  - R1: 1-month (21-day) total return reversal, ranked across sectors.
        Long Bottom 3 sectors (50% equity total, equal-weight); Short SPY beta-cancelled.
  - L1: 12-1 momentum ranking. Long Top 3 sectors (50% equity total, equal-weight);
        Short Bottom 3 sectors (equal-weight, beta-cancelled).

Gate A Hurdle Criteria (2000–2022 In-Sample):
  1. Annualized Sharpe Ratio >= 0.50 (net of costs, rf = 0.0%).
  2. CAGR on total equity >= 4.00%.
  3. Maximum Drawdown >= -20.00% (magnitude <= 20.0%).
  4. Worst Single Month >= -8.00% (magnitude <= 8.0%).
  5. Market Neutrality: Realized beta to SPY in [-0.15, +0.15] AND |corr| <= 0.35.
  6. Consistency: Positive in >= 70.0% of rolling 3-year (36-month) windows.
  7. Turnover Frequency: Total trades per year <= 60.
  8. Deflated Sharpe Ratio (DSR) >= 0.95 with N = 3, using unit-consistent formula.
  9. Random-Selection Null Test: Sharpe > 95th percentile of 1,000 random-selection runs.

Diagnostics (Reported, not part of N):
  Winner tested with 2 and 4 sectors, and 9-month and 11-month lookbacks.
  Sharpe must stay >= 0.30 across all four variations.

Holdout (2023-01-01 to Present):
  Opened once for the single winning candidate. Must maintain positive Sharpe and MaxDD >= -20%.
"""

import os
import sys
import math
import time
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial
from trading_system.app.validation.gate_evaluator import GateEvaluator

PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "SP500_SECTOR_MARKET_NEUTRAL_PROTOCOL_V1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "SP500_SECTOR_MARKET_NEUTRAL_PROTOCOL_V1.sha256")
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "sp500_sectors_cache")
TRIAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")
RESULTS_JSON_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "phase4_sp500_sector_gate_a_results.json")

EXPECTED_PROTOCOL_HASH = "cf3c41200397f7f87d0d3e3254de32e4083e9be5f96728d36f87bc72a8d848e7"

ALL_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC", "SPY"]
SECTOR_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]

IN_SAMPLE_START = "2000-01-03"
IN_SAMPLE_END = "2022-12-30"
HOLDOUT_START = "2023-01-03"

SLIPPAGE_BPS = 2.0  # 2 bps per side
BORROW_FEE_PA = 0.0050  # 0.5% annualized drag on short market value
INITIAL_EQUITY = 100000.0


def verify_protocol_hash():
    """Verify that the protocol document matches its SHA-256 seal."""
    if not os.path.exists(PROTOCOL_PATH):
        raise FileNotFoundError(f"Protocol file not found: {PROTOCOL_PATH}")
    if not os.path.exists(PROTOCOL_SHA256_PATH):
        raise FileNotFoundError(f"Protocol SHA-256 file not found: {PROTOCOL_SHA256_PATH}")

    with open(PROTOCOL_PATH, "rb") as f:
        content = f.read()
    computed_hash = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()

    with open(PROTOCOL_SHA256_PATH, "r", encoding="utf-8") as f:
        expected_hash = f.read().strip()

    if computed_hash != expected_hash:
        raise ValueError(
            f"PROTOCOL TAMPERING DETECTED!\nComputed: {computed_hash}\nExpected: {expected_hash}"
        )
    if computed_hash != EXPECTED_PROTOCOL_HASH:
        raise ValueError(
            f"PROTOCOL HASH MISMATCH!\nComputed: {computed_hash}\nExpected Constant: {EXPECTED_PROTOCOL_HASH}"
        )
    print(f"[OK] Protocol verified: {computed_hash}")


def load_dataset() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load split- and dividend-adjusted Close and Open panels from parquet cache."""
    closes = {}
    opens = {}
    for ticker in ALL_TICKERS:
        file_path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Missing cached parquet file: {file_path}. Run load_sp500_sector_data.py first.")
        df = pd.read_parquet(file_path)
        closes[ticker] = df["close"]
        opens[ticker] = df["open"]

    close_df = pd.DataFrame(closes).sort_index()
    open_df = pd.DataFrame(opens).sort_index()
    return close_df, open_df


def compute_individual_rolling_betas(close_df: pd.DataFrame, lookback: int = 126) -> pd.DataFrame:
    """Precompute 126-day rolling OLS beta to SPY for each sector ETF."""
    spy_ret = close_df["SPY"].pct_change()
    spy_var = spy_ret.rolling(lookback).var()
    betas = {}

    for s in SECTOR_TICKERS:
        s_ret = close_df[s].pct_change()
        cov = s_ret.rolling(lookback).cov(spy_ret)
        b = cov / spy_var
        betas[s] = b.fillna(1.0).clip(0.50, 1.50)

    beta_df = pd.DataFrame(betas, index=close_df.index)
    return beta_df


def simulate_strategy(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    beta_df: pd.DataFrame,
    strategy_id: str,
    lookback_months: int = 12,
    skip_months: int = 1,
    n_sectors: int = 3,
    start_date: str = IN_SAMPLE_START,
    end_date: str = IN_SAMPLE_END,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Simulates monthly rebalanced market-neutral sector strategy with next-open fills,
    beta hedging, 2 bps slippage each way, and 0.5% p.a. borrow cost on short leg.
    """
    month_ends = [d for d in close_df.groupby([close_df.index.year, close_df.index.month]).tail(1).index]
    trading_days = [d for d in close_df.index if d >= pd.to_datetime(start_date) and d <= pd.to_datetime(end_date)]

    # Fast mapping of month ends to next trading session open
    me_idx = close_df.index.get_indexer(month_ends)
    rebal_map = {month_ends[i]: close_df.index[me_idx[i] + 1] for i in range(len(month_ends)) if me_idx[i] + 1 < len(close_df.index)}

    decisions = {}
    for me in month_ends:
        exec_day = rebal_map.get(me)
        if not exec_day or exec_day > trading_days[-1] or exec_day < trading_days[0]:
            continue

        idx_me = month_ends.index(me)
        eligible = []
        scores = {}

        for s in SECTOR_TICKERS:
            s_close = close_df[s].dropna()
            if s_close.empty or s_close.index[0] > me:
                continue

            if strategy_id in ["M1", "L1"]:
                if idx_me < lookback_months:
                    continue
                t_skip = month_ends[idx_me - skip_months]
                t_lookback = month_ends[idx_me - lookback_months]
                if t_lookback in s_close.index and t_skip in s_close.index:
                    p_skip = s_close.loc[t_skip]
                    p_lookback = s_close.loc[t_lookback]
                    if p_lookback > 0:
                        scores[s] = (p_skip / p_lookback) - 1.0
                        eligible.append(s)
            elif strategy_id == "R1":
                if idx_me < 1:
                    continue
                t_prev = month_ends[idx_me - 1]
                if t_prev in s_close.index and me in s_close.index:
                    scores[s] = (s_close.loc[me] / s_close.loc[t_prev]) - 1.0
                    eligible.append(s)

        if len(eligible) < n_sectors:
            continue

        if strategy_id in ["M1", "L1"]:
            sorted_sectors = sorted(eligible, key=lambda s: scores[s], reverse=True)
            long_picks = sorted_sectors[:n_sectors]
            short_picks = sorted_sectors[-n_sectors:] if strategy_id == "L1" else ["SPY"]
        elif strategy_id == "R1":
            sorted_sectors = sorted(eligible, key=lambda s: scores[s], reverse=False)
            long_picks = sorted_sectors[:n_sectors]
            short_picks = ["SPY"]

        # Long leg beta is the mean of individual sector rolling betas
        beta_long = float(np.clip(beta_df.loc[me, long_picks].mean(), 0.50, 1.50))
        w_long_total = 0.50

        if strategy_id in ["M1", "R1"]:
            w_spy = - w_long_total * beta_long
            gross = w_long_total + abs(w_spy)
            scale = 1.0 if gross <= 1.0 else 1.0 / gross
            weights = {s: (w_long_total / n_sectors) * scale for s in long_picks}
            weights["SPY"] = w_spy * scale
        else:  # L1
            beta_short = float(np.clip(beta_df.loc[me, short_picks].mean(), 0.50, 1.50))
            ratio = float(np.clip(beta_long / beta_short, 0.50, 2.0))
            w_short_total = - w_long_total * ratio
            gross = w_long_total + abs(w_short_total)
            scale = 1.0 if gross <= 1.0 else 1.0 / gross
            weights = {s: (w_long_total / n_sectors) * scale for s in long_picks}
            for s in short_picks:
                weights[s] = (w_short_total / n_sectors) * scale

        decisions[exec_day] = weights

    # Daily simulation
    cash = INITIAL_EQUITY
    current_shares = {}
    total_trades = 0
    history = []

    for day in trading_days:
        if day in decisions:
            new_target_weights = decisions[day]
            equity_at_open = cash + sum(sh * open_df.at[day, s] for s, sh in current_shares.items())
            target_dollars = {s: w * equity_at_open for s, w in new_target_weights.items()}

            turnover = 0.0
            new_shares = {}
            for s, target_val in target_dollars.items():
                p_open = open_df.at[day, s]
                sh = target_val / p_open
                old_sh = current_shares.get(s, 0.0)
                diff = abs(sh - old_sh)
                turnover += diff * p_open
                new_shares[s] = sh
                if diff * p_open > 10.0:
                    total_trades += 1

            for s, old_sh in current_shares.items():
                if s not in new_target_weights:
                    p_open = open_df.at[day, s]
                    diff = abs(old_sh)
                    turnover += diff * p_open
                    if diff * p_open > 10.0:
                        total_trades += 1

            slippage = turnover * (SLIPPAGE_BPS / 10000.0)
            cash = equity_at_open - slippage - sum(new_shares[s] * open_df.at[day, s] for s in new_shares)
            current_shares = new_shares

        # Daily borrow fee on short positions
        short_val = sum(abs(sh * close_df.at[day, s]) for s, sh in current_shares.items() if sh < 0)
        daily_borrow = short_val * (BORROW_FEE_PA / 252.0)
        cash -= daily_borrow

        pos_val = sum(sh * close_df.at[day, s] for s, sh in current_shares.items())
        total_equity = cash + pos_val
        history.append({"date": day, "equity": total_equity})

    res_df = pd.DataFrame(history).set_index("date")
    res_df["ret"] = res_df["equity"].pct_change().fillna(0.0)

    # Compute statistics
    days = len(res_df)
    years = days / 252.0
    end_eq = res_df["equity"].iloc[-1]
    cagr = (end_eq / INITIAL_EQUITY) ** (1.0 / years) - 1.0

    mean_ret = res_df["ret"].mean()
    std_ret = res_df["ret"].std()
    sharpe = float((mean_ret / std_ret) * np.sqrt(252)) if std_ret > 0 else 0.0

    cummax = res_df["equity"].cummax()
    dd = (res_df["equity"] - cummax) / cummax
    max_dd = float(dd.min())

    monthly_eq = res_df["equity"].resample("ME").last()
    monthly_rets = monthly_eq.pct_change().dropna()
    worst_month = float(monthly_rets.min()) if len(monthly_rets) > 0 else 0.0

    spy_rets = close_df.loc[res_df.index, "SPY"].pct_change().fillna(0.0)
    cov = np.cov(res_df["ret"], spy_rets)[0, 1]
    var_spy = np.var(spy_rets)
    beta = float(cov / var_spy) if var_spy > 0 else 0.0
    corr = float(np.corrcoef(res_df["ret"], spy_rets)[0, 1])

    roll_3y = monthly_rets.rolling(36).apply(lambda x: (1 + x).prod() - 1.0).dropna()
    pct_pos_3y = float((roll_3y > 0).mean()) if len(roll_3y) > 0 else 0.0
    trades_per_yr = float(total_trades / years)

    metrics = {
        "strategy_id": strategy_id,
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "worst_month_pct": round(worst_month * 100.0, 2),
        "beta_to_spy": round(beta, 4),
        "corr_to_spy": round(corr, 4),
        "rolling_3y_pos_pct": round(pct_pos_3y * 100.0, 1),
        "trades_per_year": round(trades_per_yr, 1),
        "ending_equity": round(end_eq, 2),
    }

    return res_df, metrics


def run_random_null_test_vectorized(
    close_df: pd.DataFrame,
    beta_df: pd.DataFrame,
    n_runs: int = 1000
) -> Tuple[float, List[float]]:
    """
    Runs 1,000 Monte Carlo runs selecting 3 random sectors each month with identical
    beta hedge, 2 bps slippage, and 0.5% borrow cost using vectorized daily return math.
    """
    print(f"\nExecuting Vectorized Random-Selection Null Test ({n_runs} runs)...", flush=True)
    t0 = time.time()
    month_ends = [d for d in close_df.groupby([close_df.index.year, close_df.index.month]).tail(1).index]
    me_idx = close_df.index.get_indexer(month_ends)
    rebal_map = {month_ends[i]: close_df.index[me_idx[i] + 1] for i in range(len(month_ends)) if me_idx[i] + 1 < len(close_df.index)}

    in_sample_days = [d for d in close_df.index if d >= pd.to_datetime(IN_SAMPLE_START) and d <= pd.to_datetime(IN_SAMPLE_END)]
    in_sample_me = [me for me in month_ends if me in rebal_map and rebal_map[me] in in_sample_days]
    eligible_at_me = {me: [s for s in SECTOR_TICKERS if close_df[s].first_valid_index() <= me] for me in month_ends}

    # Precompute in-sample daily returns matrix
    in_sample_rets = close_df.loc[in_sample_days].pct_change().fillna(0.0)
    day_to_month_idx = {}
    for i, me in enumerate(in_sample_me):
        exec_day = rebal_map[me]
        next_exec = rebal_map[in_sample_me[i + 1]] if i + 1 < len(in_sample_me) else in_sample_days[-1]
        for d in in_sample_days:
            if exec_day <= d <= next_exec:
                day_to_month_idx[d] = me

    null_sharpes = []
    daily_borrow_rate = BORROW_FEE_PA / 252.0

    for seed in range(n_runs):
        rng = np.random.RandomState(seed + 1000)
        # Compute monthly weights
        weights_by_me = {}
        for me in in_sample_me:
            el = eligible_at_me[me]
            picks = list(rng.choice(el, size=3, replace=False))
            b_long = float(np.clip(beta_df.loc[me, picks].mean(), 0.50, 1.50))
            w_spy = - 0.50 * b_long
            gross = 0.50 + abs(w_spy)
            scale = 1.0 if gross <= 1.0 else 1.0 / gross
            w_dict = {s: (0.50 / 3.0) * scale for s in picks}
            w_dict["SPY"] = w_spy * scale
            weights_by_me[me] = (w_dict, w_spy * scale)

        # Build daily portfolio return series
        daily_rets = []
        prev_w = {}
        for d in in_sample_days:
            me = day_to_month_idx.get(d)
            if not me:
                daily_rets.append(0.0)
                continue
            w_dict, w_spy = weights_by_me[me]
            ret_d = sum(w * in_sample_rets.at[d, s] for s, w in w_dict.items())
            # Deduct short borrow fee
            ret_d -= abs(w_spy) * daily_borrow_rate
            # Rebalance day slippage
            if d in rebal_map.values():
                all_s = set(w_dict) | set(prev_w)
                turnover = sum(abs(w_dict.get(s, 0.0) - prev_w.get(s, 0.0)) for s in all_s)
                ret_d -= turnover * (SLIPPAGE_BPS / 10000.0)
                prev_w = w_dict
            daily_rets.append(ret_d)

        r_arr = np.array(daily_rets)
        sh = float((np.mean(r_arr) / np.std(r_arr)) * np.sqrt(252)) if np.std(r_arr) > 0 else 0.0
        null_sharpes.append(round(sh, 4))

        if (seed + 1) % 250 == 0:
            print(f"  Completed {seed + 1} / {n_runs} null iterations...", flush=True)

    p95 = float(np.percentile(null_sharpes, 95))
    print(f"Vectorized Null Test completed in {time.time() - t0:.2f}s. p95: {p95:.4f}, Mean: {np.mean(null_sharpes):.4f}", flush=True)
    return p95, null_sharpes


def compute_dsr(rets: pd.Series, sharpe: float, n_trials: int = 3) -> float:
    """Computes Deflated Sharpe Ratio strictly per Amendment V1.2 unit-consistent formula."""
    num_obs = len(rets)
    skew = float(rets.skew()) if num_obs > 2 else 0.0
    kurt = float(rets.kurtosis() + 3.0) if num_obs > 3 else 3.0
    var_sharpe = 0.164  # Prior variance across trial family

    dsr = GateEvaluator.compute_deflated_sharpe(
        sharpe=sharpe,
        num_trials=n_trials,
        num_observations=num_obs,
        skewness=skew,
        kurtosis=kurt,
        var_sharpe=var_sharpe,
        annualized=True
    )
    return float(dsr)


def evaluate_gate_a():
    """Main Gate A evaluation orchestration."""
    print("=" * 75)
    print("PHASE 4 GATE A EVALUATION: S&P 500 SECTOR MARKET-NEUTRAL BOT")
    print("=" * 75, flush=True)

    verify_protocol_hash()
    close_df, open_df = load_dataset()
    beta_df = compute_individual_rolling_betas(close_df, lookback=126)

    candidates = ["M1", "R1", "L1"]
    results = {}
    candidate_dfs = {}

    for cid in candidates:
        print(f"\nRunning In-Sample Simulation for Candidate {cid} (2000–2022)...", flush=True)
        df_sim, m = simulate_strategy(close_df, open_df, beta_df, strategy_id=cid)
        dsr = compute_dsr(df_sim["ret"], m["sharpe_ratio"], n_trials=3)
        m["deflated_sharpe_ratio"] = round(dsr, 4)
        results[cid] = m
        candidate_dfs[cid] = df_sim
        print(f"  -> {cid}: CAGR={m['cagr_pct']}%, MaxDD={m['max_drawdown_pct']}%, Sharpe={m['sharpe_ratio']}, DSR={dsr:.4f}", flush=True)

    # Random null test (vectorized for rapid execution)
    p95_null, null_sharpes = run_random_null_test_vectorized(close_df, beta_df, n_runs=1000)
    print(f"\nRandom-Selection Null 95th Percentile Sharpe: {p95_null:.4f}", flush=True)

    # Evaluate Hurdles for each candidate
    hurdles_check = {}
    passed_candidates = []

    print("\n" + "=" * 75)
    print("GATE A HURDLE VERIFICATION MATRIX (In-Sample 2000–2022)")
    print("=" * 75, flush=True)

    for cid in candidates:
        m = results[cid]
        h1 = m["sharpe_ratio"] >= 0.50
        h2 = m["cagr_pct"] >= 4.00
        h3 = m["max_drawdown_pct"] >= -20.00
        h4 = m["worst_month_pct"] >= -8.00
        h5 = (-0.15 <= m["beta_to_spy"] <= 0.15) and (abs(m["corr_to_spy"]) <= 0.35)
        h6 = m["rolling_3y_pos_pct"] >= 70.0
        h7 = m["trades_per_year"] <= 60.0
        h8 = m["deflated_sharpe_ratio"] >= 0.95
        h9 = m["sharpe_ratio"] > p95_null

        all_pass = all([h1, h2, h3, h4, h5, h6, h7, h8, h9])
        hurdles_check[cid] = {
            "H1_Sharpe_0.50": {"val": m["sharpe_ratio"], "pass": h1},
            "H2_CAGR_4.0%": {"val": m["cagr_pct"], "pass": h2},
            "H3_MaxDD_-20.0%": {"val": m["max_drawdown_pct"], "pass": h3},
            "H4_WorstMonth_-8.0%": {"val": m["worst_month_pct"], "pass": h4},
            "H5_Beta_Neutrality": {"beta": m["beta_to_spy"], "corr": m["corr_to_spy"], "pass": h5},
            "H6_Rolling_3Y_Pos_70%": {"val": m["rolling_3y_pos_pct"], "pass": h6},
            "H7_Turnover_60": {"val": m["trades_per_year"], "pass": h7},
            "H8_DSR_0.95": {"val": m["deflated_sharpe_ratio"], "pass": h8},
            "H9_Null_p95": {"null_p95": round(p95_null, 4), "pass": h9},
            "ALL_PASS": all_pass
        }

        print(f"\nCandidate {cid}: {'CLEARED GATE A' if all_pass else 'FAILED GATE A'}", flush=True)
        print(f"  1. Sharpe Ratio >= 0.50             : {'PASS' if h1 else 'FAIL'} (Val: {m['sharpe_ratio']})")
        print(f"  2. CAGR >= 4.00%                    : {'PASS' if h2 else 'FAIL'} (Val: {m['cagr_pct']}%)")
        print(f"  3. Max Drawdown >= -20.00%          : {'PASS' if h3 else 'FAIL'} (Val: {m['max_drawdown_pct']}%)")
        print(f"  4. Worst Single Month >= -8.00%     : {'PASS' if h4 else 'FAIL'} (Val: {m['worst_month_pct']}%)")
        print(f"  5. Market Neutrality (|b|<=.15,|r|<=.35): {'PASS' if h5 else 'FAIL'} (Beta: {m['beta_to_spy']}, Corr: {m['corr_to_spy']})")
        print(f"  6. Rolling 3Y Positive >= 70.0%     : {'PASS' if h6 else 'FAIL'} (Val: {m['rolling_3y_pos_pct']}%)")
        print(f"  7. Trades / Year <= 60              : {'PASS' if h7 else 'FAIL'} (Val: {m['trades_per_year']})")
        print(f"  8. Deflated Sharpe >= 0.95 (N=3)    : {'PASS' if h8 else 'FAIL'} (Val: {m['deflated_sharpe_ratio']})")
        print(f"  9. Random Null Test (Sharpe > p95)  : {'PASS' if h9 else 'FAIL'} (Val: {m['sharpe_ratio']} vs p95: {p95_null:.4f})", flush=True)

        if all_pass:
            passed_candidates.append(cid)

    # Determine Winner
    winner_cid = None
    if passed_candidates:
        winner_cid = max(passed_candidates, key=lambda c: results[c]["sharpe_ratio"])
        print(f"\n>>> CHAMPION CANDIDATE: {winner_cid} (Sharpe={results[winner_cid]['sharpe_ratio']})", flush=True)
    else:
        winner_cid = max(candidates, key=lambda c: results[c]["sharpe_ratio"])
        print(f"\n>>> NO CANDIDATE CLEARED ALL 9 HURDLES. Best performer: {winner_cid} (Sharpe={results[winner_cid]['sharpe_ratio']})", flush=True)

    # Diagnostics for top candidate (Reported, not part of N)
    print("\n" + "=" * 75)
    print(f"PARAMETER SENSITIVITY DIAGNOSTICS FOR {winner_cid} (Hurdle: Sharpe >= 0.30)")
    print("=" * 75, flush=True)
    diagnostics = {}
    diag_configs = [
        {"name": "2_sectors", "n_sec": 2, "lb": 12, "skip": 1},
        {"name": "4_sectors", "n_sec": 4, "lb": 12, "skip": 1},
        {"name": "9m_lookback", "n_sec": 3, "lb": 9, "skip": 1},
        {"name": "11m_lookback", "n_sec": 3, "lb": 11, "skip": 1},
    ]
    for cfg in diag_configs:
        _, m_diag = simulate_strategy(
            close_df, open_df, beta_df,
            strategy_id=winner_cid,
            lookback_months=cfg["lb"],
            skip_months=cfg["skip"],
            n_sectors=cfg["n_sec"]
        )
        d_pass = m_diag["sharpe_ratio"] >= 0.30
        diagnostics[cfg["name"]] = {"metrics": m_diag, "pass": d_pass}
        print(f"  - {cfg['name']} (N={cfg['n_sec']}, LB={cfg['lb']}m): Sharpe={m_diag['sharpe_ratio']:.4f}, CAGR={m_diag['cagr_pct']}%, MaxDD={m_diag['max_drawdown_pct']}% -> {'PASS' if d_pass else 'FAIL'}", flush=True)

    # Holdout Window Evaluation for Winner (opened once)
    print("\n" + "=" * 75)
    print(f"OUT-OF-SAMPLE HOLDOUT EVALUATION FOR {winner_cid} (2023-01-03 to Present)")
    print("=" * 75, flush=True)
    df_ho, m_ho = simulate_strategy(
        close_df, open_df, beta_df,
        strategy_id=winner_cid,
        start_date=HOLDOUT_START,
        end_date=close_df.index[-1].strftime("%Y-%m-%d")
    )
    dsr_ho = compute_dsr(df_ho["ret"], m_ho["sharpe_ratio"], n_trials=3)
    m_ho["deflated_sharpe_ratio"] = round(dsr_ho, 4)
    ho_pass = (m_ho["sharpe_ratio"] > 0.0) and (m_ho["max_drawdown_pct"] >= -20.00)
    print(f"  Holdout Period   : {HOLDOUT_START} to {close_df.index[-1].strftime('%Y-%m-%d')}")
    print(f"  CAGR             : {m_ho['cagr_pct']}%")
    print(f"  Sharpe Ratio     : {m_ho['sharpe_ratio']} (Hurdle: > 0.0 -> {'PASS' if m_ho['sharpe_ratio'] > 0 else 'FAIL'})")
    print(f"  Max Drawdown     : {m_ho['max_drawdown_pct']}% (Hurdle: >= -20.00% -> {'PASS' if m_ho['max_drawdown_pct'] >= -20 else 'FAIL'})")
    print(f"  Beta to SPY      : {m_ho['beta_to_spy']}")
    print(f"  Holdout Verdict  : {'PASS' if ho_pass else 'FAIL'}", flush=True)

    # Stamp trials into canonical trial_log.csv
    print("\nStamping N = 3 trials into canonical trial_log.csv...", flush=True)
    current_commit = "unknown"
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            current_commit = res.stdout.strip()
    except Exception:
        pass

    for cid in candidates:
        m = results[cid]
        log_trial(
            cagr_pct=m["cagr_pct"],
            max_drawdown_pct=m["max_drawdown_pct"],
            sharpe_ratio=m["sharpe_ratio"],
            kelly_fraction=0.00,  # Unleveraged equity
            lookback_days=252 if cid in ["M1", "L1"] else 21,
            is_holdout_opened=(cid == winner_cid),
            commit_hash=current_commit,
            script="run_phase4_sp500_sector_gate_a.py",
            universe="SP500_SECTORS_11_PLUS_SPY",
            notes=f"Phase 4 Gate A {cid}: In-Sample 2000-2022. Passed={hurdles_check[cid]['ALL_PASS']}. DSR={m['deflated_sharpe_ratio']:.4f}."
        )

    # Save comprehensive results JSON
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runner_commit": current_commit,
        "protocol_hash": EXPECTED_PROTOCOL_HASH,
        "declared_trials_n": 3,
        "in_sample_window": {"start": IN_SAMPLE_START, "end": IN_SAMPLE_END},
        "holdout_window": {"start": HOLDOUT_START, "end": close_df.index[-1].strftime("%Y-%m-%d")},
        "null_test_p95_sharpe": round(p95_null, 4),
        "candidates": results,
        "hurdles_verification": hurdles_check,
        "champion_selected": winner_cid if passed_candidates else None,
        "gate_a_cleared": len(passed_candidates) > 0,
        "diagnostics": diagnostics,
        "holdout_results": m_ho,
    }

    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Results successfully saved to {RESULTS_JSON_PATH}", flush=True)

    return payload


if __name__ == "__main__":
    evaluate_gate_a()
