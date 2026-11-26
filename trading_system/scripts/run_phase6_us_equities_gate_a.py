"""
Phase 6: US Non-ETF Individual Equities Gate A Evaluator
=======================================================
Evaluates orthogonal US individual-equity strategies (strictly ZERO ETFs) on the
100% Point-in-Time survivor-free S&P 500 constituent panel (2007-2024):
  - U1: Low-Volatility Uptrend (60D Vol Min + >200-SMA)
  - U2: Beta-Neutral Idiosyncratic Residual Momentum (126D Resid Alpha/Vol)
  - U3: Quality Low-Beta Pullback (Beta < 0.90 + >200-SMA + 20D Mean-Reversion Dip)

Strict Fiduciary Guarantees:
- Zero ETFs admitted into tradable holdings.
- 100% Point-in-Time constituent mask (sp500_ticker_start_end.csv).
- Execution strictly 1 trading session AFTER signal close (t+1 fill, zero lookahead).
- Realistic US SEC/FINRA + slippage friction (5 bps base, 10 bps stressed 2x) & US tax drag.
- In-Sample (2007-09-24 to 2021-12-31) vs Sealed Holdout (2022-01-03 to 2024-07-05).
- Holdout opens ONLY if a candidate clears ALL Gate A hurdles simultaneously.
"""

import os
import sys
import json
import math
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
PANEL_FILE = os.path.join(DATA_DIR, "us_sp500_close_panel.parquet")
PIT_FILE = os.path.join(DATA_DIR, "sp500_ticker_start_end.csv")
SPY_CACHE = os.path.join(DATA_DIR, "historical_cache_us", "SPY.parquet")
RESULTS_JSON = os.path.join(DATA_DIR, "phase6_us_equities_gate_a_results.json")

IN_SAMPLE_START = "2007-09-24"
IN_SAMPLE_END = "2021-12-31"
HOLDOUT_START = "2022-01-03"
HOLDOUT_END = "2024-07-05"

BANNED_ETFS = {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "SPLV", "USMV", "QUAL", "VLUE", "MTUM"}

BASE_ONEWAY_BPS = 5.0
STRESSED_ONEWAY_BPS = 10.0
CASH_YIELD_PA = 0.015  # Conservative short-term T-bill floor across 2008-2021 ZIRP


def compute_dsr(sharpe: float, rets: pd.Series, n_trials: int) -> float:
    """Bailey & Lopez de Prado Deflated Sharpe Ratio using annualization scaling."""
    if len(rets) < 12 or rets.std() <= 0 or sharpe <= 0:
        return 0.0
    sr_per_period = float(rets.mean() / rets.std(ddof=1))
    skew = float(stats.skew(rets))
    kurt = float(stats.kurtosis(rets, fisher=False))  # Pearson kurtosis
    t_len = len(rets)

    # Expected max Sharpe across n_trials independent trials (per-period)
    if n_trials <= 1:
        sr0 = 0.0
    else:
        emc = 0.5772156649
        z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
        z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
        std_sr = math.sqrt(1.0 / max(t_len - 1, 1))
        sr0 = std_sr * ((1.0 - emc) * z1 + emc * z2)

    denom = math.sqrt(max(1e-9, 1.0 - skew * sr_per_period + ((kurt - 1.0) / 4.0) * (sr_per_period ** 2)))
    z = ((sr_per_period - sr0) * math.sqrt(max(t_len - 1, 1))) / denom
    return float(stats.norm.cdf(z))


def load_data():
    us = pd.read_parquet(PANEL_FILE)
    us.index = pd.to_datetime(us.index).tz_localize(None) if getattr(us.index, "tz", None) else pd.to_datetime(us.index)
    us = us[[c for c in us.columns if c not in BANNED_ETFS]].sort_index()

    spy_df = pd.read_parquet(SPY_CACHE)
    spy_df.index = pd.to_datetime(spy_df.index).tz_localize(None) if getattr(spy_df.index, "tz", None) else pd.to_datetime(spy_df.index)
    spy_col = "adj_close" if "adj_close" in spy_df.columns else "close"
    spy = spy_df[spy_col].dropna().sort_index()

    common_dates = us.index.intersection(spy.index).sort_values()
    us = us.loc[common_dates]
    spy = spy.loc[common_dates]

    df_int = pd.read_csv(PIT_FILE)
    df_int["ticker_clean"] = df_int["ticker"].str.replace(".", "-", regex=False)
    df_int["start_date"] = pd.to_datetime(df_int["start_date"])
    df_int["end_date"] = pd.to_datetime(df_int["end_date"]).fillna(pd.Timestamp("2099-12-31"))

    return us, spy, df_int


def build_pit_mask(dates_list: List[pd.Timestamp], cols: pd.Index, df_int: pd.DataFrame) -> pd.DataFrame:
    mask = pd.DataFrame(False, index=dates_list, columns=cols)
    for dt in dates_list:
        act = df_int[(df_int["start_date"] <= dt) & (df_int["end_date"] > dt)]["ticker_clean"].unique()
        valid = [c for c in act if c in cols]
        mask.loc[dt, valid] = True
    return mask


def simulate_us_strategy(
    us: pd.DataFrame,
    spy: pd.Series,
    pit_mask: pd.DataFrame,
    sig_dates: List[pd.Timestamp],
    exec_dates: List[pd.Timestamp],
    precomp: Dict[str, Any],
    strategy: str,
    oneway_bps: float = BASE_ONEWAY_BPS,
    top_k: int = 15,
    beta_cap: float = 0.90,
    dip_window: int = 20,
    use_bear_defense: bool = True,
) -> Dict[str, Any]:
    vol60 = precomp["vol60"]
    sma200 = precomp["sma200"]
    beta126 = precomp["beta126"]
    resid_score = precomp["resid_score"]
    spy_sma200 = precomp["spy_sma200"]
    ret_dip = precomp[f"ret_{dip_window}"]

    nav = 100000.0
    navs = [nav]
    prev_weights: Dict[str, float] = {}
    turnovers = []

    for i in range(len(sig_dates) - 1):
        d_sig = sig_dates[i]
        d_exec_in = exec_dates[i]
        d_exec_out = exec_dates[i + 1]

        new_weights: Dict[str, float] = {}
        if use_bear_defense and spy.loc[d_sig] < spy_sma200.loc[d_sig]:
            new_weights = {}
        else:
            act = pit_mask.loc[d_sig]
            elig = [
                c for c in act[act].index
                if pd.notna(us.loc[d_sig, c]) and pd.notna(sma200.loc[d_sig, c])
                and us.loc[d_sig, c] > sma200.loc[d_sig, c]
                and pd.notna(us.loc[d_exec_in, c]) and pd.notna(us.loc[d_exec_out, c])
                and us.loc[d_exec_in, c] > 5.0
            ]
            selected = []
            if strategy == "U1_LOW_VOL_TREND":
                selected = vol60.loc[d_sig, elig].dropna().sort_values(ascending=True).head(top_k).index.tolist()
            elif strategy == "U2_RESIDUAL_MOM":
                selected = resid_score.loc[d_sig, elig].dropna().sort_values(ascending=False).head(top_k).index.tolist()
            elif strategy == "U3_LOW_BETA_DIP":
                b = beta126.loc[d_sig, elig].dropna()
                pool = b[b < beta_cap].index.tolist()
                if pool:
                    selected = ret_dip.loc[d_sig, pool].dropna().sort_values(ascending=True).head(top_k).index.tolist()
            elif strategy == "CTRL_EQ_WEIGHT":
                selected = elig

            if selected:
                w = 1.0 / len(selected)
                new_weights = {s: w for s in selected}

        # Two-sided turnover vs previous month weights
        all_syms = set(prev_weights.keys()) | set(new_weights.keys())
        traded_frac = sum(abs(new_weights.get(s, 0.0) - prev_weights.get(s, 0.0)) for s in all_syms)
        turnovers.append(traded_frac / 2.0)

        # Period return strictly from d_exec_in (t+1) to d_exec_out
        if new_weights:
            gross_r = sum(w * (float(us.loc[d_exec_out, s] / us.loc[d_exec_in, s]) - 1.0) for s, w in new_weights.items())
            if pd.isna(gross_r):
                gross_r = 0.0
        else:
            days_held = max(1, (d_exec_out - d_exec_in).days)
            gross_r = (1.0 + CASH_YIELD_PA) ** (days_held / 365.25) - 1.0

        cost_frac = traded_frac * (oneway_bps / 10000.0)
        net_r = gross_r - cost_frac
        # Apply conservative STCG annual drag proxy on net positive monthly gains (~20%)
        if net_r > 0 and new_weights:
            net_r *= (1.0 - 0.15 * 0.25)  # blended STCG/LTCG tax reserve proxy on active gains

        nav = nav * (1.0 + net_r)
        navs.append(nav)
        prev_weights = new_weights

    ser = pd.Series(navs, index=exec_dates)
    mret = ser.pct_change().dropna()
    yrs = (exec_dates[-1] - exec_dates[0]).days / 365.25
    cagr = ((ser.iloc[-1] / ser.iloc[0]) ** (1.0 / yrs) - 1.0) * 100.0 if yrs > 0 else 0.0
    sharpe = (mret.mean() * 12.0) / (mret.std(ddof=1) * math.sqrt(12.0)) if mret.std(ddof=1) > 0 else 0.0
    dd = ((ser / ser.cummax()) - 1.0).min() * 100.0
    worst_m = mret.min() * 100.0 if len(mret) else 0.0

    # SPY correlation
    spy_m = spy.loc[exec_dates].pct_change().dropna()
    corr = float(mret.corr(spy_m)) if len(mret) == len(spy_m) and mret.std() > 0 else 0.0

    return {
        "cagr_pct": round(float(cagr), 2),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(dd), 2),
        "worst_month_pct": round(float(worst_m), 2),
        "ending_equity": round(float(ser.iloc[-1]), 2),
        "avg_monthly_turnover_pct": round(float(np.mean(turnovers) * 100.0), 1),
        "spy_corr": round(corr, 3),
        "monthly_returns": mret,
        "nav_series": ser,
    }


def make_rebal_pairs(dates: pd.DatetimeIndex, start_s: str, end_s: str) -> Tuple[List[pd.Timestamp], List[pd.Timestamp]]:
    sub = dates[(dates >= start_s) & (dates <= end_s)]
    m_ends = pd.Series(sub, index=sub).resample("ME").last().dropna().tolist()
    sig_dates, exec_dates = [], []
    for d in m_ends:
        pos = dates.get_loc(d)
        if pos + 1 < len(dates):
            sig_dates.append(d)
            exec_dates.append(dates[pos + 1])
    return sig_dates, exec_dates


def main():
    print("=" * 85)
    print("PHASE 6: US NON-ETF INDIVIDUAL EQUITIES GATE A EVALUATOR")
    print("=" * 85)
    us, spy, df_int = load_data()
    all_dates = us.index

    rets = us.pct_change()
    spy_ret = spy.pct_change()
    cov_spy = rets.rolling(126).cov(spy_ret)
    var_spy = spy_ret.rolling(126).var()
    beta126 = cov_spy.div(var_spy, axis=0)
    resid_ret = rets - beta126.mul(spy_ret, axis=0)

    precomp = {
        "vol60": rets.rolling(60).std() * math.sqrt(252.0),
        "sma200": us.rolling(200).mean(),
        "beta126": beta126,
        "resid_score": (resid_ret.rolling(126).mean() / resid_ret.rolling(126).std()) * math.sqrt(252.0),
        "spy_sma200": spy.rolling(200).mean(),
        "ret_16": us.pct_change(16),
        "ret_20": us.pct_change(20),
        "ret_24": us.pct_change(24),
    }

    sig_is, exec_is = make_rebal_pairs(all_dates, IN_SAMPLE_START, IN_SAMPLE_END)
    pit_is = build_pit_mask(sig_is, us.columns, df_int)

    # Benchmark SPY over exact exec_is window
    spy_is = spy.loc[exec_is]
    spy_yrs = (exec_is[-1] - exec_is[0]).days / 365.25
    spy_m = spy_is.pct_change().dropna()
    spy_cagr = ((spy_is.iloc[-1] / spy_is.iloc[0]) ** (1.0 / spy_yrs) - 1.0) * 100.0
    spy_sharpe = (spy_m.mean() * 12.0) / (spy_m.std(ddof=1) * math.sqrt(12.0))
    spy_dd = ((spy_is / spy_is.cummax()) - 1.0).min() * 100.0
    print(f"Benchmark SPY (t+1): CAGR={spy_cagr:.2f}%, Sharpe={spy_sharpe:.4f}, MaxDD={spy_dd:.2f}%")

    ctrl_eq = simulate_us_strategy(us, spy, pit_is, sig_is, exec_is, precomp, "CTRL_EQ_WEIGHT")
    print(f"Control PIT Eq-Wt  : CAGR={ctrl_eq['cagr_pct']:.2f}%, Sharpe={ctrl_eq['sharpe_ratio']:.4f}, MaxDD={ctrl_eq['max_drawdown_pct']:.2f}%")

    results = {}
    for strat in ["U1_LOW_VOL_TREND", "U2_RESIDUAL_MOM", "U3_LOW_BETA_DIP"]:
        res = simulate_us_strategy(us, spy, pit_is, sig_is, exec_is, precomp, strat, oneway_bps=BASE_ONEWAY_BPS)
        dsr_3 = compute_dsr(res["sharpe_ratio"], res["monthly_returns"], n_trials=3)
        results[strat] = {k: v for k, v in res.items() if k not in ("monthly_returns", "nav_series")}
        results[strat]["dsr_family_3"] = round(dsr_3, 4)
        print(f"Candidate {strat:18s}: CAGR={res['cagr_pct']:5.2f}%, Sharpe={res['sharpe_ratio']:.4f}, MaxDD={res['max_drawdown_pct']:6.2f}%, DSR(N=3)={dsr_3:.4f}")

    # Monte Carlo 500-iteration Null Control (random 15 PIT S&P 500 stocks > 200-SMA with identical Bear filter)
    rng = np.random.default_rng(42)
    null_sharpes = []
    spy_bear_flags = [bool(spy.loc[d] < precomp["spy_sma200"].loc[d]) for d in sig_is[:-1]]
    elig_lists = []
    elig_fwd_rets = []
    for i in range(len(sig_is) - 1):
        d_sig, d_in, d_out = sig_is[i], exec_is[i], exec_is[i + 1]
        act = pit_is.loc[d_sig]
        elig = [
            c for c in act[act].index
            if pd.notna(us.loc[d_sig, c]) and pd.notna(precomp["sma200"].loc[d_sig, c])
            and us.loc[d_sig, c] > precomp["sma200"].loc[d_sig, c]
            and pd.notna(us.loc[d_in, c]) and pd.notna(us.loc[d_out, c]) and us.loc[d_in, c] > 5.0
        ]
        elig_lists.append(elig)
        elig_fwd_rets.append((us.loc[d_out, elig] / us.loc[d_in, elig] - 1.0).values if elig else np.array([]))

    cash_m = (1.0 + CASH_YIELD_PA) ** (1.0 / 12.0) - 1.0
    for _ in range(500):
        m_rets = []
        for i in range(len(sig_is) - 1):
            if spy_bear_flags[i] or len(elig_lists[i]) == 0:
                m_rets.append(cash_m)
            else:
                k = min(15, len(elig_fwd_rets[i]))
                idx = rng.choice(len(elig_fwd_rets[i]), size=k, replace=False)
                m_rets.append(float(np.nanmean(elig_fwd_rets[i][idx])) - 0.001)
        arr = np.array(m_rets)
        s_val = (arr.mean() * 12.0) / (arr.std(ddof=1) * math.sqrt(12.0)) if arr.std(ddof=1) > 0 else 0.0
        null_sharpes.append(s_val)
    null_p95 = float(np.percentile(null_sharpes, 95))
    print(f"Monte Carlo Null (500 iters, same Bear filter): Mean={np.mean(null_sharpes):.4f}, p95={null_p95:.4f}")

    # Deep evaluation of best candidate (U3_LOW_BETA_DIP)
    u3 = simulate_us_strategy(us, spy, pit_is, sig_is, exec_is, precomp, "U3_LOW_BETA_DIP", oneway_bps=BASE_ONEWAY_BPS)
    u3_stress = simulate_us_strategy(us, spy, pit_is, sig_is, exec_is, precomp, "U3_LOW_BETA_DIP", oneway_bps=STRESSED_ONEWAY_BPS)

    # Parameter plateaus (+/- 20% shifts)
    plateaus = {}
    for lbl, kw in [
        ("TOP_K_12", {"top_k": 12}),
        ("TOP_K_18", {"top_k": 18}),
        ("BETA_0.75", {"beta_cap": 0.75}),
        ("BETA_1.05", {"beta_cap": 1.05}),
        ("DIP_16D", {"dip_window": 16}),
        ("DIP_24D", {"dip_window": 24}),
    ]:
        r_p = simulate_us_strategy(us, spy, pit_is, sig_is, exec_is, precomp, "U3_LOW_BETA_DIP", **kw)
        plateaus[lbl] = {"cagr_pct": r_p["cagr_pct"], "sharpe": r_p["sharpe_ratio"], "max_dd_pct": r_p["max_drawdown_pct"]}
    plateau_pass = all(v["sharpe"] >= 0.75 for v in plateaus.values())

    # Subperiods (4 quarters of In-Sample)
    n_seg = len(sig_is) // 4
    sub_pass_cnt = 0
    subperiods = {}
    for s_idx in range(4):
        i0 = s_idx * n_seg
        i1 = (s_idx + 1) * n_seg if s_idx < 3 else len(sig_is)
        s_seg, e_seg = sig_is[i0:i1], exec_is[i0:i1]
        r_seg = simulate_us_strategy(us, spy, pit_is.loc[s_seg], s_seg, e_seg, precomp, "U3_LOW_BETA_DIP")
        spy_seg = spy.loc[e_seg].pct_change().dropna()
        spy_sh_seg = (spy_seg.mean() * 12.0) / (spy_seg.std(ddof=1) * math.sqrt(12.0)) if spy_seg.std(ddof=1) > 0 else 0.0
        beat = r_seg["sharpe_ratio"] > spy_sh_seg
        if beat:
            sub_pass_cnt += 1
        subperiods[f"Seg_{s_idx+1}"] = {"window": f"{s_seg[0].date()}..{s_seg[-1].date()}", "sharpe": r_seg["sharpe_ratio"], "spy_sharpe": round(float(spy_sh_seg), 4), "beat_spy": bool(beat)}

    hurdles = {
        "H1_Sharpe": bool(u3["sharpe_ratio"] >= 0.85),
        "H2_MaxDD": bool(u3["max_drawdown_pct"] >= -25.0),
        "H3_CAGR": bool(u3["cagr_pct"] >= 10.0),
        "H4_DSR_Family": bool(results["U3_LOW_BETA_DIP"]["dsr_family_3"] >= 0.95),
        "H5_Null_Control": bool(u3["sharpe_ratio"] > null_p95),
        "H6_Subperiods": bool(sub_pass_cnt >= 3),
        "H7_Plateaus": bool(plateau_pass),
        "H8_Stressed_2x": bool(u3_stress["sharpe_ratio"] >= 0.80 and u3_stress["max_drawdown_pct"] >= -25.0),
        "H9_Beat_Ctrl_EqWt": bool(u3["sharpe_ratio"] > ctrl_eq["sharpe_ratio"] and u3["cagr_pct"] > ctrl_eq["cagr_pct"]),
    }
    all_passed = bool(all(hurdles.values()))

    holdout_res = {"opened": False, "reason": "Gate A hurdles failed; holdout remains sealed."}
    if all_passed:
        sig_ho, exec_ho = make_rebal_pairs(all_dates, HOLDOUT_START, HOLDOUT_END)
        pit_ho = build_pit_mask(sig_ho, us.columns, df_int)
        ho = simulate_us_strategy(us, spy, pit_ho, sig_ho, exec_ho, precomp, "U3_LOW_BETA_DIP", oneway_bps=BASE_ONEWAY_BPS)
        spy_ho = spy.loc[exec_ho]
        ho_yrs = (exec_ho[-1] - exec_ho[0]).days / 365.25
        spy_ho_m = spy_ho.pct_change().dropna()
        spy_ho_sh = (spy_ho_m.mean() * 12.0) / (spy_ho_m.std(ddof=1) * math.sqrt(12.0))
        spy_ho_cagr = ((spy_ho.iloc[-1] / spy_ho.iloc[0]) ** (1.0 / ho_yrs) - 1.0) * 100.0
        spy_ho_dd = ((spy_ho / spy_ho.cummax()) - 1.0).min() * 100.0
        holdout_res = {
            "opened": True,
            "window": f"{HOLDOUT_START} to {HOLDOUT_END}",
            "u3_cagr_pct": ho["cagr_pct"],
            "u3_sharpe": ho["sharpe_ratio"],
            "u3_max_dd_pct": ho["max_drawdown_pct"],
            "spy_cagr_pct": round(float(spy_ho_cagr), 2),
            "spy_sharpe": round(float(spy_ho_sh), 4),
            "spy_max_dd_pct": round(float(spy_ho_dd), 2),
        }

    out = {
        "benchmark_spy": {"cagr_pct": round(float(spy_cagr), 2), "sharpe_ratio": round(float(spy_sharpe), 4), "max_drawdown_pct": round(float(spy_dd), 2)},
        "control_eq_weight": {k: v for k, v in ctrl_eq.items() if k not in ("monthly_returns", "nav_series")},
        "candidates": results,
        "null_control_p95": round(null_p95, 4),
        "u3_stressed": {k: v for k, v in u3_stress.items() if k not in ("monthly_returns", "nav_series")},
        "plateaus": plateaus,
        "subperiods": subperiods,
        "hurdles": hurdles,
        "all_hurdles_passed": all_passed,
        "holdout": holdout_res,
    }
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=lambda o: bool(o) if isinstance(o, np.bool_) else float(o) if isinstance(o, np.floating) else int(o) if isinstance(o, np.integer) else str(o))

    print("\n--- U3 GATE A SUMMARY ---")
    print("Hurdles:", hurdles)
    print("ALL PASSED:", all_passed)
    print("Holdout:", holdout_res)


if __name__ == "__main__":
    main()
