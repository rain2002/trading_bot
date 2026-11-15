"""
Phase 4.1 Gate A Simulation: Factor-ETF Market-Neutral Test
===========================================================
Executes the pre-registered protocol:
  - Base Protocol: PROTOCOL-FACTOR-ETF-MARKET-NEUTRAL-V1-20261115
    (SHA-256: ee358f4d929402018e874d670dc341cb5779c935e30dd91ea36f1fb00c808e24)

Candidates Evaluated (Declared Trial Family N = 5):
  - F1: SPLV (Invesco S&P 500 Low Volatility ETF) + SPY beta hedge
  - F2: USMV (iShares MSCI USA Min Vol Factor ETF) + SPY beta hedge
  - F3: QUAL (iShares MSCI USA Quality Factor ETF) + SPY beta hedge
  - F4: VLUE (iShares MSCI USA Value Factor ETF) + SPY beta hedge
  - F5: MTUM (iShares MSCI USA Momentum Factor ETF) + SPY beta hedge

Gate A Hurdle Criteria (In-Sample through 2022-12-30):
  1. Annualized Sharpe Ratio >= 0.50 (net of costs, rf = 0.0%).
  2. CAGR on total equity >= 4.00%.
  3. Maximum Drawdown >= -20.00% (magnitude <= 20.0%).
  4. Worst Single Month >= -8.00% (magnitude <= 8.0%).
  5. Market Neutrality: Realized beta to SPY in [-0.15, +0.15] AND |corr| <= 0.35.
  6. Consistency: Positive in >= 70.0% of rolling 3-year (36-month) windows.
  7. Turnover Frequency: Total trades per year <= 24.
  8. Deflated Sharpe Ratio (DSR) >= 0.95 with N = 5, using unit-consistent formula.
  9. 15-ETF Control Null Test: Sharpe > 95th percentile of 15 control ETFs hedged identically.

Diagnostics (Reported, not hurdles):
  - Annual alpha against SPY with t-statistic from monthly returns.
  - Sub-period stability: Sharpe in first half vs second half.
  - Consistency between SPLV and USMV.

Holdout (2023-01-03 to Present):
  Strictly sealed. Opened once if and only if a candidate clears all 9 hurdles.
"""

import os
import sys
import math
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

PROTOCOL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "FACTOR_ETF_MARKET_NEUTRAL_PROTOCOL_V1.md")
PROTOCOL_SHA256_PATH = os.path.join(PROJECT_ROOT, "trading_system", "docs", "FACTOR_ETF_MARKET_NEUTRAL_PROTOCOL_V1.sha256")
CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "sp500_sectors_cache")
TRIAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")
RESULTS_JSON_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "phase4_factor_etf_gate_a_results.json")

EXPECTED_PROTOCOL_HASH = "ee358f4d929402018e874d670dc341cb5779c935e30dd91ea36f1fb00c808e24"

CANDIDATES = {
    "F1": {"ticker": "SPLV", "name": "Invesco S&P 500 Low Volatility ETF"},
    "F2": {"ticker": "USMV", "name": "iShares MSCI USA Min Vol Factor ETF"},
    "F3": {"ticker": "QUAL", "name": "iShares MSCI USA Quality Factor ETF"},
    "F4": {"ticker": "VLUE", "name": "iShares MSCI USA Value Factor ETF"},
    "F5": {"ticker": "MTUM", "name": "iShares MSCI USA Momentum Factor ETF"},
}

CONTROL_ETFS = [
    # 11 Sector SPDRs
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC",
    # 4 Size & Style Controls
    "MDY", "IWM", "QQQ", "DIA"
]

ALL_REQUIRED_TICKERS = list(set(["SPY"] + [c["ticker"] for c in CANDIDATES.values()] + CONTROL_ETFS))

IN_SAMPLE_END = "2022-12-30"
HOLDOUT_START = "2023-01-03"

SLIPPAGE_BPS = 2.0  # 2 bps per side
BORROW_FEE_PA = 0.0050  # 0.5% annualized drag on short market value
INITIAL_EQUITY = 100000.0
BETA_LOOKBACK = 126  # ~6 months daily rolling window


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
    for ticker in ALL_REQUIRED_TICKERS:
        file_path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Missing cached parquet file: {file_path}. Run load_sp500_sector_data.py first.")
        df = pd.read_parquet(file_path)
        closes[ticker] = df["close"]
        opens[ticker] = df["open"]

    close_df = pd.DataFrame(closes).sort_index()
    open_df = pd.DataFrame(opens).sort_index()
    return close_df, open_df


def compute_rolling_beta(asset_series: pd.Series, spy_series: pd.Series, lookback: int = 126) -> pd.Series:
    """Compute rolling OLS beta of asset to SPY, clamped to [0.50, 1.00]."""
    ret_asset = asset_series.pct_change()
    ret_spy = spy_series.pct_change()
    cov = ret_asset.rolling(lookback).cov(ret_spy)
    var = ret_spy.rolling(lookback).var()
    raw_beta = cov / var
    # Protocol rule: clamped to [0.50, 1.00]
    return raw_beta.clip(0.50, 1.00).fillna(1.00)


def simulate_factor_market_neutral(
    target_ticker: str,
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Simulates a long factor ETF / short SPY beta-neutral strategy with:
      - Long leg: 100% of equity in factor ETF
      - Short leg: SPY sized at -beta * equity (clamped to [-1.00, -0.50])
      - Monthly beta refresh at month-end close; fills at next-open with 2 bps slippage each way
      - 0.5% p.a. borrow fee on short SPY
      - Cash earns 0.0% interest
    """
    s_close = close_df[target_ticker].dropna()
    spy_close = close_df["SPY"].dropna()
    common_idx = s_close.index.intersection(spy_close.index)

    # Compute rolling beta
    beta_series = compute_rolling_beta(s_close.loc[common_idx], spy_close.loc[common_idx], lookback=BETA_LOOKBACK)

    # Valid trading days within [start_date, end_date]
    valid_days = [d for d in common_idx if pd.to_datetime(start_date) <= d <= pd.to_datetime(end_date)]
    if len(valid_days) < 20:
        raise ValueError(f"Insufficient trading days ({len(valid_days)}) for {target_ticker} between {start_date} and {end_date}")

    month_ends = [d for d in common_idx.to_series().groupby([common_idx.year, common_idx.month]).tail(1).values]
    me_idx = common_idx.get_indexer(month_ends)
    rebal_map = {month_ends[i]: common_idx[me_idx[i] + 1] for i in range(len(month_ends)) if me_idx[i] + 1 < len(common_idx)}

    # Daily simulation
    cash = INITIAL_EQUITY
    current_shares = {target_ticker: 0.0, "SPY": 0.0}
    total_trades = 0
    history = []
    first_day = True

    for day in valid_days:
        is_rebal_day = (day in rebal_map.values())
        
        # Initial entry on first trading day or monthly rebalance
        if first_day or is_rebal_day:
            equity_at_open = cash + sum(sh * open_df.at[day, s] for s, sh in current_shares.items())
            if equity_at_open <= 0:
                break

            # Find latest available month-end beta
            prior_mes = [me for me in month_ends if me < day]
            latest_me = prior_mes[-1] if prior_mes else day
            curr_beta = float(beta_series.loc[:latest_me].iloc[-1]) if latest_me in beta_series.index else 1.0

            # Target weights
            w_long = 1.00
            w_spy = -curr_beta  # in [-1.00, -0.50]

            target_val_long = w_long * equity_at_open
            target_val_spy = w_spy * equity_at_open

            p_open_target = open_df.at[day, target_ticker]
            p_open_spy = open_df.at[day, "SPY"]

            new_sh_target = target_val_long / p_open_target
            new_sh_spy = target_val_spy / p_open_spy

            turnover = 0.0
            for sym, new_sh, p_open in [(target_ticker, new_sh_target, p_open_target), ("SPY", new_sh_spy, p_open_spy)]:
                old_sh = current_shares.get(sym, 0.0)
                diff = abs(new_sh - old_sh)
                turnover += diff * p_open
                if diff * p_open > 10.0:
                    total_trades += 1

            slippage = turnover * (SLIPPAGE_BPS / 10000.0)
            cash = equity_at_open - slippage - (new_sh_target * p_open_target) - (new_sh_spy * p_open_spy)
            current_shares = {target_ticker: new_sh_target, "SPY": new_sh_spy}
            first_day = False

        # Assess daily borrow fee on short SPY
        short_val = abs(current_shares["SPY"] * close_df.at[day, "SPY"]) if current_shares["SPY"] < 0 else 0.0
        daily_borrow = short_val * (BORROW_FEE_PA / 252.0)
        cash -= daily_borrow

        total_equity = cash + (current_shares[target_ticker] * close_df.at[day, target_ticker]) + (current_shares["SPY"] * close_df.at[day, "SPY"])
        history.append({"date": day, "equity": total_equity})

    res_df = pd.DataFrame(history).set_index("date")
    res_df["ret"] = res_df["equity"].pct_change().fillna(0.0)

    # Statistics
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
    realized_beta = float(cov / var_spy) if var_spy > 0 else 0.0
    realized_corr = float(np.corrcoef(res_df["ret"], spy_rets)[0, 1])

    roll_3y = monthly_rets.rolling(36).apply(lambda x: (1 + x).prod() - 1.0).dropna()
    pct_pos_3y = float((roll_3y > 0).mean()) if len(roll_3y) > 0 else 0.0
    trades_per_yr = float(total_trades / years)

    # Jensen's alpha against SPY from monthly returns
    spy_monthly = close_df.loc[monthly_eq.index, "SPY"].pct_change().dropna()
    common_m = monthly_rets.index.intersection(spy_monthly.index)
    if len(common_m) > 12:
        slope, intercept, r_val, p_val, std_err = stats.linregress(spy_monthly.loc[common_m], monthly_rets.loc[common_m])
        annual_alpha_pct = float(intercept * 12 * 100.0)
        alpha_tstat = float(intercept / std_err) if std_err > 0 else 0.0
    else:
        annual_alpha_pct = 0.0
        alpha_tstat = 0.0

    # Sub-period stability (first half vs second half)
    half_pt = len(res_df) // 2
    df_h1 = res_df.iloc[:half_pt]
    df_h2 = res_df.iloc[half_pt:]
    sharpe_h1 = float((df_h1["ret"].mean() / df_h1["ret"].std()) * np.sqrt(252)) if df_h1["ret"].std() > 0 else 0.0
    sharpe_h2 = float((df_h2["ret"].mean() / df_h2["ret"].std()) * np.sqrt(252)) if df_h2["ret"].std() > 0 else 0.0

    metrics = {
        "ticker": target_ticker,
        "cagr_pct": round(cagr * 100.0, 2),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "worst_month_pct": round(worst_month * 100.0, 2),
        "realized_beta": round(realized_beta, 4),
        "realized_corr": round(realized_corr, 4),
        "rolling_3y_positive_pct": round(pct_pos_3y * 100.0, 1),
        "trades_per_year": round(trades_per_yr, 1),
        "annual_alpha_pct": round(annual_alpha_pct, 2),
        "alpha_tstat": round(alpha_tstat, 2),
        "sharpe_first_half": round(sharpe_h1, 4),
        "sharpe_second_half": round(sharpe_h2, 4),
        "years": round(years, 2),
        "total_days": days,
    }
    return res_df, metrics


def compute_dsr(returns: pd.Series, sharpe_val: float, n_trials: int = 5) -> float:
    """Compute Deflated Sharpe Ratio with unit-consistent standard error."""
    T = len(returns)
    if T < 30 or sharpe_val <= 0:
        return 0.0

    skew = returns.skew()
    kurt = returns.kurtosis()  # Excess kurtosis

    # Standard error of annualized Sharpe ratio (Lo 2002)
    # se = sqrt((1 - skew*SR + (kurt-1)/4 * SR^2) / T) where SR is annualized
    sr_annual = sharpe_val
    sr_daily = returns.mean() / returns.std() if returns.std() > 0 else 0.0
    se_daily = math.sqrt(max(1e-6, (1.0 - skew * sr_daily + (kurt / 4.0) * (sr_daily ** 2)) / T))
    se_annual = se_daily * math.sqrt(252)

    # Expected maximum Sharpe of N independent trials under null (Euler-Mascheroni approx)
    gamma = 0.5772156649
    if n_trials > 1:
        e_max_z = (1.0 - gamma) * stats.norm.ppf(1.0 - 1.0 / n_trials) + gamma * stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    else:
        e_max_z = 0.0
    e_max_sr = max(0.0, float(e_max_z * se_annual))

    dsr = float(stats.norm.cdf((sr_annual - e_max_sr) / se_annual)) if se_annual > 0 else 0.0
    return dsr


def evaluate_gate_a():
    """Main execution orchestrating Gate A evaluation across N = 5 candidates and 15 controls."""
    print("=" * 75)
    print("PHASE 4.1 GATE A EVALUATION: FACTOR-ETF MARKET-NEUTRAL TEST")
    print("=" * 75, flush=True)

    verify_protocol_hash()
    close_df, open_df = load_dataset()

    results = {}
    return_series = {}
    candidate_start_dates = {}

    print("\nRunning In-Sample Simulations for Factor Candidates (N = 5)...", flush=True)
    for cid, info in CANDIDATES.items():
        ticker = info["ticker"]
        s_series = close_df[ticker].dropna()
        # Active start is after BETA_LOOKBACK bars
        if len(s_series) <= BETA_LOOKBACK:
            raise ValueError(f"Insufficient history for {ticker}")
        sim_start = s_series.index[BETA_LOOKBACK].strftime("%Y-%m-%d")
        candidate_start_dates[cid] = sim_start

        res_df, m = simulate_factor_market_neutral(
            ticker, close_df, open_df,
            start_date=sim_start,
            end_date=IN_SAMPLE_END
        )
        dsr = compute_dsr(res_df["ret"], m["sharpe_ratio"], n_trials=5)
        m["deflated_sharpe_ratio"] = round(dsr, 4)
        m["sim_start_date"] = sim_start
        m["sim_end_date"] = IN_SAMPLE_END
        m["candidate_id"] = cid

        results[cid] = m
        return_series[cid] = res_df
        print(f"  -> {cid} ({ticker}): In-Sample {sim_start} to {IN_SAMPLE_END} ({m['years']} yrs): CAGR={m['cagr_pct']}%, MaxDD={m['max_drawdown_pct']}%, Sharpe={m['sharpe_ratio']}, DSR={m['deflated_sharpe_ratio']}", flush=True)

    # Run 15 Control ETFs to build empirical null distribution for each candidate window
    print("\nRunning 15 Control ETFs to build Control Null Distribution...", flush=True)
    control_results = {}
    for cid, info in CANDIDATES.items():
        sim_start = candidate_start_dates[cid]
        control_sharpes = []
        for c_ticker in CONTROL_ETFS:
            c_series = close_df[c_ticker].dropna()
            # If control exists over this window
            if c_series.index[0].strftime("%Y-%m-%d") <= sim_start:
                try:
                    _, m_ctrl = simulate_factor_market_neutral(c_ticker, close_df, open_df, start_date=sim_start, end_date=IN_SAMPLE_END)
                    control_sharpes.append(m_ctrl["sharpe_ratio"])
                except Exception:
                    pass
        p95_ctrl = float(np.percentile(control_sharpes, 95)) if control_sharpes else 0.50
        control_results[cid] = {
            "control_count": len(control_sharpes),
            "p95_sharpe": round(p95_ctrl, 4),
            "mean_sharpe": round(float(np.mean(control_sharpes)), 4) if control_sharpes else 0.0,
            "max_sharpe": round(float(np.max(control_sharpes)), 4) if control_sharpes else 0.0,
        }
        print(f"  -> Controls for {cid} ({info['ticker']}): N={len(control_sharpes)}, Mean Sharpe={control_results[cid]['mean_sharpe']}, p95 Sharpe={control_results[cid]['p95_sharpe']}", flush=True)

    # Verification against all 9 Gate A hurdles
    print("\n" + "=" * 75)
    print("GATE A HURDLE VERIFICATION MATRIX (In-Sample through 2022-12-30)")
    print("=" * 75, flush=True)

    hurdles_check = {}
    passed_candidates = []

    for cid, info in CANDIDATES.items():
        m = results[cid]
        ctrl = control_results[cid]

        h1 = m["sharpe_ratio"] >= 0.50
        h2 = m["cagr_pct"] >= 4.00
        h3 = m["max_drawdown_pct"] >= -20.00
        h4 = m["worst_month_pct"] >= -8.00
        h5 = (-0.15 <= m["realized_beta"] <= 0.15) and (abs(m["realized_corr"]) <= 0.35)
        h6 = m["rolling_3y_positive_pct"] >= 70.0
        h7 = m["trades_per_year"] <= 24.0
        h8 = m["deflated_sharpe_ratio"] >= 0.95
        h9 = m["sharpe_ratio"] > ctrl["p95_sharpe"]

        all_pass = all([h1, h2, h3, h4, h5, h6, h7, h8, h9])
        hurdles_check[cid] = {
            "H1_sharpe": bool(h1),
            "H2_cagr": bool(h2),
            "H3_maxdd": bool(h3),
            "H4_worst_month": bool(h4),
            "H5_market_neutrality": bool(h5),
            "H6_consistency": bool(h6),
            "H7_turnover": bool(h7),
            "H8_deflated_sharpe": bool(h8),
            "H9_control_null": bool(h9),
            "ALL_PASS": bool(all_pass),
        }

        print(f"\nCandidate {cid} ({info['ticker']} - {info['name']}): {'PASSED GATE A' if all_pass else 'FAILED GATE A'}")
        print(f"  1. Sharpe Ratio >= 0.50             : {'PASS' if h1 else 'FAIL'} (Val: {m['sharpe_ratio']})")
        print(f"  2. CAGR >= 4.00%                    : {'PASS' if h2 else 'FAIL'} (Val: {m['cagr_pct']}%)")
        print(f"  3. Max Drawdown >= -20.00%          : {'PASS' if h3 else 'FAIL'} (Val: {m['max_drawdown_pct']}%)")
        print(f"  4. Worst Single Month >= -8.00%     : {'PASS' if h4 else 'FAIL'} (Val: {m['worst_month_pct']}%)")
        print(f"  5. Market Neutrality (|b|<=.15,|r|<=.35): {'PASS' if h5 else 'FAIL'} (Beta: {m['realized_beta']}, Corr: {m['realized_corr']})")
        print(f"  6. Rolling 3Y Positive >= 70.0%     : {'PASS' if h6 else 'FAIL'} (Val: {m['rolling_3y_positive_pct']}%)")
        print(f"  7. Trades / Year <= 24              : {'PASS' if h7 else 'FAIL'} (Val: {m['trades_per_year']})")
        print(f"  8. Deflated Sharpe >= 0.95 (N=5)    : {'PASS' if h8 else 'FAIL'} (Val: {m['deflated_sharpe_ratio']})")
        print(f"  9. Control Null (Sharpe > p95)      : {'PASS' if h9 else 'FAIL'} (Val: {m['sharpe_ratio']} vs Ctrl p95: {ctrl['p95_sharpe']})")

        if all_pass:
            passed_candidates.append(cid)

    # Determine Champion strictly if cleared all 9 hurdles
    champion_cid = None
    if passed_candidates:
        champion_cid = max(passed_candidates, key=lambda c: results[c]["deflated_sharpe_ratio"])
        print(f"\n>>> CHAMPION CANDIDATE: {champion_cid} ({CANDIDATES[champion_cid]['ticker']}) - DSR={results[champion_cid]['deflated_sharpe_ratio']}", flush=True)
    else:
        best_performer = max(CANDIDATES.keys(), key=lambda c: results[c]["sharpe_ratio"])
        print(f"\n>>> NO CANDIDATE CLEARED ALL 9 HURDLES. Best performer (unapproved): {best_performer} ({CANDIDATES[best_performer]['ticker']}) with Sharpe={results[best_performer]['sharpe_ratio']}", flush=True)

    # Reported Non-Hurdle Diagnostics
    print("\n" + "=" * 75)
    print("REPORTED NON-HURDLE DIAGNOSTICS")
    print("=" * 75, flush=True)
    for cid, info in CANDIDATES.items():
        m = results[cid]
        print(f"  - {cid} ({info['ticker']}): Alpha={m['annual_alpha_pct']}% p.a. (t={m['alpha_tstat']}), H1 Sharpe={m['sharpe_first_half']}, H2 Sharpe={m['sharpe_second_half']}")
    # Low-vol consistency check
    splv_sh = results["F1"]["sharpe_ratio"]
    usmv_sh = results["F2"]["sharpe_ratio"]
    print(f"\n  Low-Vol Consistency (SPLV vs USMV): SPLV Sharpe={splv_sh}, USMV Sharpe={usmv_sh} (Diff={abs(splv_sh - usmv_sh):.4f})")

    # Holdout Window Evaluation: STRICTLY CONDITIONAL ON CLEARING ALL 9 GATE A HURDLES
    m_ho = {}
    if champion_cid is not None:
        champ_ticker = CANDIDATES[champion_cid]["ticker"]
        print("\n" + "=" * 75)
        print(f"OUT-OF-SAMPLE HOLDOUT EVALUATION FOR CHAMPION {champion_cid} ({champ_ticker}) ({HOLDOUT_START} to Present)")
        print("=" * 75, flush=True)
        df_ho, m_ho = simulate_factor_market_neutral(
            champ_ticker, close_df, open_df,
            start_date=HOLDOUT_START,
            end_date=close_df.index[-1].strftime("%Y-%m-%d")
        )
        dsr_ho = compute_dsr(df_ho["ret"], m_ho["sharpe_ratio"], n_trials=5)
        m_ho["deflated_sharpe_ratio"] = round(dsr_ho, 4)
        ho_pass = (m_ho["sharpe_ratio"] > 0.0) and (m_ho["max_drawdown_pct"] >= -20.00)
        m_ho["opened"] = True
        m_ho["pass"] = bool(ho_pass)
        print(f"  Holdout Period   : {HOLDOUT_START} to {close_df.index[-1].strftime('%Y-%m-%d')}")
        print(f"  CAGR             : {m_ho['cagr_pct']}%")
        print(f"  Sharpe Ratio     : {m_ho['sharpe_ratio']} (Hurdle: > 0.0 -> {'PASS' if m_ho['sharpe_ratio'] > 0 else 'FAIL'})")
        print(f"  Max Drawdown     : {m_ho['max_drawdown_pct']}% (Hurdle: >= -20.00% -> {'PASS' if m_ho['max_drawdown_pct'] >= -20 else 'FAIL'})")
        print(f"  Beta to SPY      : {m_ho['realized_beta']}")
        print(f"  Holdout Verdict  : {'PASS' if ho_pass else 'FAIL'}", flush=True)
    else:
        print("\n" + "=" * 75)
        print(f"OUT-OF-SAMPLE HOLDOUT GUARD: SEALED ({HOLDOUT_START} to Present)")
        print("No candidate passed all 9 Gate A hurdles. Holdout was NOT opened.")
        print("=" * 75, flush=True)
        m_ho = {
            "opened": False,
            "reason": "No candidate passed all 9 Gate A hurdles; holdout strictly sealed."
        }

    # Stamp trials into canonical trial_log.csv
    print("\nStamping N = 5 trials into canonical trial_log.csv...", flush=True)
    current_commit = "unknown"
    try:
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            current_commit = res.stdout.strip()
    except Exception:
        pass

    for cid in CANDIDATES.keys():
        m = results[cid]
        ticker = CANDIDATES[cid]["ticker"]
        log_trial(
            cagr_pct=m["cagr_pct"],
            max_drawdown_pct=m["max_drawdown_pct"],
            sharpe_ratio=m["sharpe_ratio"],
            kelly_fraction=0.00,  # Unleveraged equity
            lookback_days=BETA_LOOKBACK,
            is_holdout_opened=(cid == champion_cid and champion_cid is not None),
            commit_hash=current_commit,
            script="run_phase4_factor_etf_gate_a.py",
            universe=f"FACTOR_ETF_{ticker}_PLUS_SPY",
            notes=f"Phase 4.1 Gate A {cid} ({ticker}): In-Sample {m['sim_start_date']} to {IN_SAMPLE_END}. Passed={hurdles_check[cid]['ALL_PASS']}. DSR={m['deflated_sharpe_ratio']:.4f}."
        )

    # Save comprehensive results JSON with robust serializer
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runner_commit": current_commit,
        "protocol_hash": EXPECTED_PROTOCOL_HASH,
        "declared_trials_n": 5,
        "candidates": results,
        "control_null_results": control_results,
        "hurdles_verification": hurdles_check,
        "champion_selected": champion_cid,
        "gate_a_cleared": len(passed_candidates) > 0,
        "holdout_results": m_ho,
    }

    def json_serial(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=json_serial)
    print(f"Results successfully saved to {RESULTS_JSON_PATH}", flush=True)

    return payload


if __name__ == "__main__":
    evaluate_gate_a()
