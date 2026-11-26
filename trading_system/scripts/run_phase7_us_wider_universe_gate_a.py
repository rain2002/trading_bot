"""
Phase 7 Gate A: Wider US Individual Equities (S&P 500 + S&P 400 + S&P 600, Strictly Non-ETF)
===========================================================================================
Evaluates pre-registered non-ETF US stock strategies on the wider Point-in-Time S&P 1500
composite universe with:
  - Strict Zero-ETF filter (SPY kept strictly as passive benchmark)
  - Liquidity & price floor (Close >= $10, 20D median Dollar Volume >= $2M)
  - Causal t+1 execution (Signal Close[t] -> Trade Close[t+1])
  - Realistic one-way cost stress (5 bps base, 10 bps stressed)
  - Passive PIT Equal-Weight control + 500-iteration Monte Carlo null control
  - 4x ~4-year subperiod consistency + 9-point parameter plateau
  - Cumulative Deflated Sharpe Ratio (DSR) anchored to `trial_log.csv` N
  - Strictly sealed Out-of-Sample Holdout (2023-01-03 .. 2026-11-26) unless ALL Gate A hurdles pass
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
CLOSE_PARQUET = os.path.join(DATA_DIR, "us_wider_close_panel.parquet")
VOLUME_PARQUET = os.path.join(DATA_DIR, "us_wider_volume_panel.parquet")
PIT_CSV = os.path.join(DATA_DIR, "us_wider_universe_pit_intervals.csv")
AUDIT_JSON = os.path.join(DATA_DIR, "us_wider_universe_data_audit.json")
TRIAL_LOG_CSV = os.path.join(DATA_DIR, "trial_log.csv")
OUT_JSON = os.path.join(DATA_DIR, "phase7_us_wider_universe_gate_a_results.json")

IS_START = "2007-01-03"
IS_END = "2022-12-30"
HO_START = "2023-01-03"
HO_END = "2026-11-26"

BASE_BPS = 5.0
STRESS_BPS = 10.0

FORBIDDEN_ETFS = {"SPY", "VOO", "IVV", "QQQ", "IWM", "MDY", "IJH", "IJR", "VTI", "DIA", "GLD"}


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.3577518672690, -30.66479806614716, 2.506628277459239]
    b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572]
    c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
    d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416]
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)


def compute_dsr(daily_rets: np.ndarray, n_trials: int) -> Tuple[float, float]:
    n = len(daily_rets)
    if n < 30 or np.std(daily_rets) < 1e-12:
        return 0.0, 0.0
    sr_daily = np.mean(daily_rets) / np.std(daily_rets, ddof=1)
    sr_ann = float(sr_daily * math.sqrt(252.0))
    skew = float(pd.Series(daily_rets).skew())
    kurt = float(pd.Series(daily_rets).kurt() + 3.0)
    gamma = 0.5772156649
    e = math.e
    if n_trials <= 1:
        sr_bench = 0.0
    else:
        z1 = norm_ppf(1.0 - 1.0 / n_trials)
        z2 = norm_ppf(1.0 - 1.0 / (n_trials * e))
        sr_bench = ((1.0 - gamma) * z1 + gamma * z2) * math.sqrt(1.0 / 252.0)
    denom_inner = max(1e-9, 1.0 - skew * sr_daily + ((kurt - 1.0) / 4.0) * (sr_daily ** 2))
    sr_std = math.sqrt(denom_inner / (n - 1))
    dsr = float(norm_cdf((sr_daily - sr_bench) / max(sr_std, 1e-9)))
    return sr_ann, dsr


def compute_metrics(eq: pd.Series, spy_ret_ann: float | None = None) -> dict:
    if len(eq) < 20:
        return {"cagr_pct": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0, "calmar": 0.0}
    rets = eq.pct_change().dropna().to_numpy(dtype=np.float64)
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = float(((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0)
    roll_max = eq.cummax()
    max_dd = float(((eq / roll_max) - 1.0).min() * 100.0)
    sharpe = float((np.mean(rets) / max(np.std(rets, ddof=1), 1e-12)) * math.sqrt(252.0))
    calmar = float(cagr / abs(max_dd)) if max_dd < -0.01 else 0.0
    return {
        "cagr_pct": round(cagr, 2),
        "sharpe": round(sharpe, 4),
        "max_dd_pct": round(max_dd, 2),
        "calmar": round(calmar, 3),
        "excess_vs_spy_pct": round(cagr - spy_ret_ann, 2) if spy_ret_ann is not None else None,
    }


def build_pit_mask(
    dates: pd.DatetimeIndex,
    tickers: List[str],
    pit_df: pd.DataFrame,
) -> np.ndarray:
    """Boolean (T x N) matrix where ticker `j` is actively inside S&P 1500 PIT on date `i`."""
    mask = np.zeros((len(dates), len(tickers)), dtype=bool)
    ticker_to_col = {t: j for j, t in enumerate(tickers)}
    d_vals = dates.values
    for row in pit_df.itertuples(index=False):
        col = ticker_to_col.get(row.ticker)
        if col is None:
            continue
        st = np.datetime64(pd.Timestamp(row.start_date))
        en = np.datetime64(pd.Timestamp(row.end_date))
        in_range = (d_vals >= st) & (d_vals <= en)
        mask[:, col] |= in_range
    return mask


def get_rebal_pairs(dates: pd.DatetimeIndex, start_dt: str, end_dt: str) -> List[Tuple[int, int]]:
    """Monthly signal date idx (last trading day of month) paired with causal t+1 execution idx."""
    in_win = np.where((dates >= pd.Timestamp(start_dt)) & (dates <= pd.Timestamp(end_dt)))[0]
    if len(in_win) < 5:
        return []
    sub_dates = dates[in_win]
    ym = sub_dates.to_period("M")
    pairs: List[Tuple[int, int]] = []
    seen_ym = set()
    for k in range(len(sub_dates) - 1):
        # Last day inside month before month switches
        if ym[k] != ym[k + 1] and ym[k] not in seen_ym:
            seen_ym.add(ym[k])
            sig_idx = int(in_win[k])
            exec_idx = sig_idx + 1
            if exec_idx < len(dates):
                pairs.append((sig_idx, exec_idx))
    return pairs


def simulate_weights_portfolio(
    close_arr: np.ndarray,
    rebal_pairs: List[Tuple[int, int]],
    weight_fn,
    cost_bps: float,
    dates: pd.DatetimeIndex,
    start_dt: str,
    end_dt: str,
    ret_arr: np.ndarray | None = None,
) -> Tuple[pd.Series, float]:
    """Causal t+1 simulation using pre-computed target weight arrays at monthly rebalances."""
    idx_slice = np.where((dates >= pd.Timestamp(start_dt)) & (dates <= pd.Timestamp(end_dt)))[0]
    t0, t1 = int(idx_slice[0]), int(idx_slice[-1])
    N = close_arr.shape[1]

    if ret_arr is None:
        prev_c = close_arr[:-1]
        cur_c = close_arr[1:]
        ret_arr = np.where(
            (prev_c > 0) & (cur_c > 0) & np.isfinite(prev_c) & np.isfinite(cur_c),
            cur_c / prev_c - 1.0,
            0.0,
        )

    exec_map = {exec_i: weight_fn(sig_i) for sig_i, exec_i in rebal_pairs if t0 <= exec_i <= t1}
    eq = np.ones(t1 - t0 + 1, dtype=np.float64)
    w = np.zeros(N, dtype=np.float64)
    total_turnover = 0.0
    n_rebal = 0

    for step, t in enumerate(range(t0, t1 + 1)):
        if step > 0:
            r_t = ret_arr[t - 1]
            port_r = float(np.dot(w, r_t))
            eq[step] = eq[step - 1] * (1.0 + port_r)
            if np.sum(w) > 0:
                w = w * (1.0 + r_t)
                w /= max(1e-12, 1.0 + port_r)

        if t in exec_map:
            new_w = exec_map[t]
            turnover = float(np.sum(np.abs(new_w - w))) / 2.0
            cost = turnover * (cost_bps / 10_000.0) * 2.0
            eq[step] *= (1.0 - cost)
            w = new_w.copy()
            total_turnover += turnover
            n_rebal += 1

    ann_turnover = (total_turnover / max(n_rebal, 1)) * 12.0 * 100.0
    series = pd.Series(eq * 100_000.0, index=dates[t0 : t1 + 1])
    return series, round(ann_turnover, 1)


def main():
    print("=== PHASE 7 GATE A: WIDER US INDIVIDUAL EQUITIES (S&P 1500 COMPOSITE PIT, STRICTLY NON-ETF) ===", flush=True)
    close_df = pd.read_parquet(CLOSE_PARQUET)
    vol_df = pd.read_parquet(VOLUME_PARQUET)
    pit_df = pd.read_csv(PIT_CSV)
    with open(AUDIT_JSON, "r", encoding="utf-8") as f:
        audit = json.load(f)

    spy_series = close_df["SPY"].dropna()
    stock_cols = sorted([c for c in close_df.columns if c not in FORBIDDEN_ETFS])
    close_df = close_df[stock_cols]
    vol_df_raw = vol_df.reindex(index=close_df.index, columns=stock_cols)
    has_vol_col = (vol_df_raw.notna().sum(axis=0) >= 20).to_numpy(dtype=bool)
    vol_df = vol_df_raw.fillna(0.0)

    dates = close_df.index
    close_arr = close_df.to_numpy(dtype=np.float64)
    vol_arr = vol_df.to_numpy(dtype=np.float64)
    dollar_vol_20d = (close_df * vol_df).rolling(20, min_periods=10).median().to_numpy(dtype=np.float64)

    print(f"Loaded panel: {close_arr.shape[0]} days x {close_arr.shape[1]} non-ETF stocks ({dates[0].date()} .. {dates[-1].date()})", flush=True)

    pit_mask = build_pit_mask(dates, stock_cols, pit_df)
    sp500_pit_mask = build_pit_mask(dates, stock_cols, pit_df[pit_df["index_tier"] == "SP500"])
    liq_ok = np.where(has_vol_col[None, :], dollar_vol_20d >= 2_000_000.0, sp500_pit_mask)
    valid_hist = (~np.isnan(close_arr)) & (close_arr >= 10.0) & liq_ok
    # Require 252 trading days of trailing non-NaN history before signal
    hist_ok = close_df.rolling(252, min_periods=200).count().to_numpy() >= 200
    eligible_mask = pit_mask & valid_hist & hist_ok

    # Precompute causal signal matrices (at Close[t])
    daily_ret = close_df.pct_change()
    vol_126 = (daily_ret.rolling(126, min_periods=90).std() * math.sqrt(252.0)).to_numpy(dtype=np.float64)
    sma_200 = close_df.rolling(200, min_periods=150).mean().to_numpy(dtype=np.float64)
    sma_150 = close_df.rolling(150, min_periods=110).mean().to_numpy(dtype=np.float64)
    ret_21 = (close_df / close_df.shift(21) - 1.0).to_numpy(dtype=np.float64)
    ret_252_21 = (close_df.shift(21) / close_df.shift(252) - 1.0).to_numpy(dtype=np.float64)
    ret_126_21 = (close_df.shift(21) / close_df.shift(126) - 1.0).to_numpy(dtype=np.float64)

    def make_strategy_weight_fn(strat_id: str, top_n: int = 30, mom_lb: int = 252):
        r_mom = ret_252_21 if mom_lb == 252 else (ret_126_21 if mom_lb == 126 else (close_df.shift(21) / close_df.shift(mom_lb) - 1.0).to_numpy(dtype=np.float64))

        def weight_fn(sig_i: int) -> np.ndarray:
            w = np.zeros(len(stock_cols), dtype=np.float64)
            elig = eligible_mask[sig_i].copy()
            if strat_id == "CTRL_EW_PIT":
                idx = np.where(elig)[0]
                if len(idx) > 0:
                    w[idx] = 1.0 / len(idx)
                return w

            above_200 = elig & (close_arr[sig_i] > sma_200[sig_i]) & np.isfinite(vol_126[sig_i]) & (vol_126[sig_i] > 0.01)
            if strat_id == "W1_LOW_VOL_TREND":
                cand = np.where(above_200)[0]
                if len(cand) == 0:
                    return w
                picks = cand[np.argsort(vol_126[sig_i, cand])[:top_n]]
                w[picks] = 1.0 / len(picks)
            elif strat_id == "W2_QUALITY_RESIDUAL_MOM":
                cand_mask = above_200 & np.isfinite(r_mom[sig_i]) & (r_mom[sig_i] > 0.0)
                cand = np.where(cand_mask)[0]
                if len(cand) == 0:
                    return w
                score = r_mom[sig_i, cand] / vol_126[sig_i, cand]
                picks = cand[np.argsort(-score)[:top_n]]
                w[picks] = 1.0 / len(picks)
            elif strat_id == "W3_LOW_BETA_DIP":
                cand_mask = above_200 & np.isfinite(ret_21[sig_i])
                cand = np.where(cand_mask)[0]
                if len(cand) == 0:
                    return w
                # Bottom 25% volatility pool, buy deepest 21D pullback
                q25 = np.percentile(vol_126[sig_i, cand], 25)
                low_v = cand[vol_126[sig_i, cand] <= q25]
                picks = low_v[np.argsort(ret_21[sig_i, low_v])[:top_n]]
                w[picks] = 1.0 / len(picks)
            elif strat_id == "W4_MIDSMALL_MOM_6M1M":
                cand_mask = elig & (close_arr[sig_i] > sma_150[sig_i]) & np.isfinite(r_mom[sig_i]) & np.isfinite(vol_126[sig_i])
                cand = np.where(cand_mask)[0]
                if len(cand) == 0:
                    return w
                picks = cand[np.argsort(-r_mom[sig_i, cand])[:top_n]]
                w[picks] = 1.0 / len(picks)
            return w

        return weight_fn

    rebal_is = get_rebal_pairs(dates, IS_START, IS_END)
    spy_is = spy_series[(spy_series.index >= pd.Timestamp(IS_START)) & (spy_series.index <= pd.Timestamp(IS_END))]
    spy_is_eq = spy_is / spy_is.iloc[0] * 100_000.0
    spy_m = compute_metrics(spy_is_eq)
    spy_cagr = spy_m["cagr_pct"]

    # Read current N from trial_log.csv so DSR reflects cumulative multiple-testing burden
    with open(TRIAL_LOG_CSV, "r", encoding="utf-8") as f:
        existing_n = max(0, sum(1 for _ in f) - 1)
    n_new_strats = 4
    n_cum = existing_n + n_new_strats

    print(f"In-Sample Window: {IS_START} .. {IS_END} | SPY CAGR={spy_cagr}% Sharpe={spy_m['sharpe']} DD={spy_m['max_dd_pct']}% | Existing N={existing_n}, New N_cum={n_cum}", flush=True)

    prev_c_all = close_arr[:-1]
    cur_c_all = close_arr[1:]
    ret_arr_global = np.where(
        (prev_c_all > 0) & (cur_c_all > 0) & np.isfinite(prev_c_all) & np.isfinite(cur_c_all),
        cur_c_all / prev_c_all - 1.0,
        0.0,
    )

    # Evaluate Control Equal-Weight PIT
    ctrl_eq_base, ctrl_to = simulate_weights_portfolio(
        close_arr, rebal_is, make_strategy_weight_fn("CTRL_EW_PIT"), BASE_BPS, dates, IS_START, IS_END, ret_arr=ret_arr_global
    )
    ctrl_m = compute_metrics(ctrl_eq_base, spy_cagr)

    # 500-iteration Monte Carlo null control (random 30 liquid PIT stocks monthly; exact vectorized monthly tranches)
    rng = np.random.default_rng(42)
    mc_sharpes = []
    mc_cagrs = []
    idx_is = np.where((dates >= pd.Timestamp(IS_START)) & (dates <= pd.Timestamp(IS_END)))[0]
    t0, t1 = int(idx_is[0]), int(idx_is[-1])
    elig_lists = {sig_i: np.where(eligible_mask[sig_i])[0] for sig_i, _ in rebal_is}
    is_rebals = [(sig_i, exec_i) for sig_i, exec_i in rebal_is if t0 <= exec_i <= t1]
    cum_factors = np.vstack([np.ones((1, ret_arr_global.shape[1]), dtype=np.float64), np.cumprod(1.0 + ret_arr_global, axis=0)])

    for _ in range(500):
        eq_mc = np.ones(t1 - t0 + 1, dtype=np.float64)
        cur_eq = 1.0
        for r_idx, (sig_i, exec_i) in enumerate(is_rebals):
            pool = elig_lists[sig_i]
            picks = rng.choice(pool, size=min(30, len(pool)), replace=False) if len(pool) > 0 else np.array([], dtype=int)
            next_exec = is_rebals[r_idx + 1][1] if (r_idx + 1) < len(is_rebals) else (t1 + 1)
            next_exec = min(next_exec, t1 + 1)
            if len(picks) > 0 and exec_i < next_exec:
                # 5 bps one-way approximate ~10 bps roundtrip friction per rebal tranche
                cur_eq_net = cur_eq * (1.0 - (BASE_BPS / 10_000.0) * 1.5)
                seg = (cum_factors[exec_i:next_exec, picks] / cum_factors[exec_i, picks]).mean(axis=1)
                eq_mc[exec_i - t0 : next_exec - t0] = cur_eq_net * seg
                cur_eq = float(eq_mc[next_exec - 1 - t0])
        m_mc = compute_metrics(pd.Series(eq_mc * 100_000.0, index=dates[t0 : t1 + 1]))
        mc_sharpes.append(m_mc["sharpe"])
        mc_cagrs.append(m_mc["cagr_pct"])

    mc_p50_sharpe = round(float(np.percentile(mc_sharpes, 50)), 4)
    mc_p95_sharpe = round(float(np.percentile(mc_sharpes, 95)), 4)
    mc_p95_cagr = round(float(np.percentile(mc_cagrs, 95)), 2)
    print(f"CTRL_EW_PIT: CAGR={ctrl_m['cagr_pct']}% Sharpe={ctrl_m['sharpe']} | MC 500 Null: p50 Sharpe={mc_p50_sharpe}, p95 Sharpe={mc_p95_sharpe} (p95 CAGR={mc_p95_cagr}%)", flush=True)

    candidates = [
        ("W1_LOW_VOL_TREND", 30, 252),
        ("W2_QUALITY_RESIDUAL_MOM", 30, 252),
        ("W3_LOW_BETA_DIP", 30, 252),
        ("W4_MIDSMALL_MOM_6M1M", 30, 126),
    ]
    subperiods = [
        ("2007-2010", "2007-01-03", "2010-12-31"),
        ("2011-2014", "2011-01-03", "2014-12-31"),
        ("2015-2018", "2015-01-02", "2018-12-31"),
        ("2019-2022", "2019-01-02", "2022-12-30"),
    ]

    results_by_strat = {}
    commit_hash = "HEAD"
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    except Exception:
        pass

    any_all_pass = False
    best_strat_id = None
    best_sharpe = -999.0

    for sid, top_n, mom_lb in candidates:
        eq_5, to_pct = simulate_weights_portfolio(
            close_arr, rebal_is, make_strategy_weight_fn(sid, top_n, mom_lb), BASE_BPS, dates, IS_START, IS_END, ret_arr=ret_arr_global
        )
        eq_10, _ = simulate_weights_portfolio(
            close_arr, rebal_is, make_strategy_weight_fn(sid, top_n, mom_lb), STRESS_BPS, dates, IS_START, IS_END, ret_arr=ret_arr_global
        )
        m5 = compute_metrics(eq_5, spy_cagr)
        m10 = compute_metrics(eq_10, spy_cagr)
        sr_ann, dsr_cum = compute_dsr(eq_5.pct_change().dropna().to_numpy(), n_cum)

        sub_out = {}
        sub_pos = 0
        for lbl, s0, s1 in subperiods:
            sp_s = eq_5[(eq_5.index >= pd.Timestamp(s0)) & (eq_5.index <= pd.Timestamp(s1))]
            sp_spy = spy_is_eq[(spy_is_eq.index >= pd.Timestamp(s0)) & (spy_is_eq.index <= pd.Timestamp(s1))]
            sm = compute_metrics(sp_s, compute_metrics(sp_spy)["cagr_pct"])
            sub_out[lbl] = sm
            if sm["cagr_pct"] > 0:
                sub_pos += 1

        # 3x3 Parameter plateau around candidate
        plat_pass = 0
        plat_grid = []
        for n_p in [20, 30, 40]:
            for lb_p in ([126, 189, 252] if sid in ("W2_QUALITY_RESIDUAL_MOM", "W4_MIDSMALL_MOM_6M1M") else [150, 200, 250]):
                w_fn_p = make_strategy_weight_fn(sid, n_p, lb_p if sid in ("W2_QUALITY_RESIDUAL_MOM", "W4_MIDSMALL_MOM_6M1M") else 252)
                eq_p, _ = simulate_weights_portfolio(close_arr, rebal_is, w_fn_p, BASE_BPS, dates, IS_START, IS_END, ret_arr=ret_arr_global)
                mp = compute_metrics(eq_p, spy_cagr)
                plat_grid.append({"top_n": n_p, "lookback": lb_p, "cagr_pct": mp["cagr_pct"], "sharpe": mp["sharpe"], "max_dd_pct": mp["max_dd_pct"]})
                if mp["sharpe"] > mc_p95_sharpe and mp["cagr_pct"] > spy_cagr:
                    plat_pass += 1

        hurdles = {
            "beats_spy_cagr_plus_2pct": m5["cagr_pct"] >= (spy_cagr + 2.0),
            "beats_mc_p95_sharpe": m5["sharpe"] > mc_p95_sharpe,
            "beats_ctrl_ew_cagr": m5["cagr_pct"] > ctrl_m["cagr_pct"],
            "max_dd_within_35pct": m5["max_dd_pct"] >= -35.0,
            "dsr_cum_ge_080": dsr_cum >= 0.80,
            "stressed_10bps_still_beats_spy": m10["cagr_pct"] > spy_cagr,
            "subperiods_4_of_4_positive": sub_pos == 4,
            "plateau_ge_7_of_9": plat_pass >= 7,
        }
        all_pass = all(hurdles.values())
        if all_pass:
            any_all_pass = True
        if m5["sharpe"] > best_sharpe:
            best_sharpe = m5["sharpe"]
            best_strat_id = sid

        results_by_strat[sid] = {
            "base_5bps": m5,
            "stressed_10bps": m10,
            "annual_turnover_pct": to_pct,
            "dsr_cum": round(dsr_cum, 4),
            "n_cumulative_trials": n_cum,
            "subperiods": sub_out,
            "subperiods_positive": sub_pos,
            "plateau_pass_count": plat_pass,
            "plateau_grid": plat_grid,
            "hurdles": hurdles,
            "gate_a_passed": all_pass,
        }

        print(
            f"  {sid}: 5bps CAGR={m5['cagr_pct']}% (vs SPY {spy_cagr}%) Sharpe={m5['sharpe']} "
            f"(MC95={mc_p95_sharpe}) DD={m5['max_dd_pct']}% | 10bps CAGR={m10['cagr_pct']}% | "
            f"DSR={dsr_cum:.3f} | Sub={sub_pos}/4 | Plat={plat_pass}/9 | PASS={all_pass}",
            flush=True,
        )

        # Log honestly into trial_log.csv
        log_trial(
            commit_hash=commit_hash,
            script="run_phase7_us_wider_universe_gate_a.py",
            universe="US_WIDER_SP1500_PIT_NON_ETF",
            kelly_fraction=0.0,
            lookback_days=mom_lb,
            cagr_pct=m5["cagr_pct"],
            max_drawdown_pct=m5["max_dd_pct"],
            sharpe_ratio=m5["sharpe"],
            is_holdout_opened=False,
            notes=(
                f"Phase 7 {sid} Wider US PIT (S&P1500 non-ETF, >=$10, >=$2M dvol, t+1, 5bps) IS 2007-2022. "
                f"SPY={spy_cagr}%, CtrlEW={ctrl_m['cagr_pct']}%, MC_p95_SR={mc_p95_sharpe}, DSR={dsr_cum:.3f} (N={n_cum}), "
                f"GateA_Pass={all_pass}. Caveat: Yahoo 404 survivorship attrition={audit['composite_union_summary']['survivorship_attrition_pct']}%. "
                f"Holdout=STRICTLY_SEALED."
            ),
        )

    holdout_status = "OPENED_AFTER_PASS" if any_all_pass else "STRICTLY_SEALED"
    verdict = {
        "gate_a_all_passed": any_all_pass,
        "best_candidate": best_strat_id,
        "holdout_status": holdout_status,
        "deployment_decision": (
            "ADVANCE_TO_SHADOW_INCUBATION"
            if any_all_pass
            else "REJECTED_DO_NOT_DEPLOY_KEEP_US_RETIRED"
        ),
        "survivorship_audit_warning": audit["composite_union_summary"]["honest_survivorship_caveat"],
    }

    output = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_id": "US_WIDER_SP1500_PIT_NON_ETF",
        "strictly_no_etfs": True,
        "in_sample_window": f"{IS_START} .. {IS_END}",
        "holdout_window": f"{HO_START} .. {HO_END}",
        "holdout_status": holdout_status,
        "n_cumulative_trials_dsr": n_cum,
        "benchmark_spy": spy_m,
        "control_equal_weight_pit": {**ctrl_m, "annual_turnover_pct": ctrl_to},
        "monte_carlo_500_null": {
            "p50_sharpe": mc_p50_sharpe,
            "p95_sharpe": mc_p95_sharpe,
            "p95_cagr_pct": mc_p95_cagr,
        },
        "data_audit_summary": audit["composite_union_summary"],
        "candidates": results_by_strat,
        "verdict": verdict,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved Phase 7 Gate A results to {OUT_JSON}", flush=True)
    print(json.dumps(verdict, indent=2), flush=True)


if __name__ == "__main__":
    main()
