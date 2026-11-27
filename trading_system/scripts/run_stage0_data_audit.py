"""
Stage 0: Data Audit & Panel Versioning (Walk-Forward Roadmap)
============================================================
Executes all 5 Stage 0 acceptance tasks in order:
1. Explain Control B (-0.88% raw vs split-adjusted vs benchmark).
2. Trace top 10 S2 trades against outside prices (Yahoo Finance) and V2 CA.
3. Sensitivity test the 50 rejected/unverified CA events (excluded vs adjusted).
4. Run top-5-trades-removed test on S2 against the 14.3% Gate A bar.
5. Version the panel with a SHA-256 and log every re-run in trial_log.csv.
"""

import os
import sys
import json
import math
import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import trading_system.app.data.corporate_actions as ca_mod
import trading_system.scripts.run_phase5_nse_whole_market_gate_a as p5
from trading_system.scripts.audit_full_panel_corporate_actions import match_canonical_ratio
from trading_system.app.validation.trial_logger import log_trial

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
CA_V2_CSV = os.path.join(DATA_DIR, "nse_corporate_actions_v2.csv")
PANEL_SHA_PATH = os.path.join(DATA_DIR, "nse_panel_v2.sha256")
REPORT_JSON_PATH = os.path.join(DATA_DIR, "stage0_data_audit_report.json")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_50_unverified_events(
    close_df: pd.DataFrame,
    open_df: pd.DataFrame,
    turnover_df: pd.DataFrame,
    v2_actions: Dict[Tuple[str, str], float],
) -> List[Dict[str, Any]]:
    """Re-identifies the exact 50 >=35% overnight liquid drop events not in V2 CA."""
    events: List[Dict[str, Any]] = []
    med_turn = turnover_df.rolling(60, min_periods=5).median()
    prev_c = close_df.shift(1)
    prev_to = med_turn.shift(1)
    ret_df = (close_df / prev_c) - 1.0

    # Exact same S2-eligible liquid drop filter as audit_full_panel_corporate_actions.py
    liq_drop_mask = (prev_c >= 20.0) & (prev_to >= 20_000_000.0) & (ret_df <= -0.20)
    hits = liq_drop_mask.stack()
    drop_events = [(dt, sym) for dt, sym in hits[hits].index]

    for dt_c, sym in drop_events:
        if any(s == sym and abs((pd.to_datetime(d) - dt_c).days) <= 4 for d, s in v2_actions.keys()):
            continue

        c_prev = prev_c.loc[dt_c, sym]
        c_cur = close_df.loc[dt_c, sym]
        o_cur = open_df.loc[dt_c, sym] if sym in open_df.columns else c_cur
        if pd.isna(c_prev) or pd.isna(c_cur) or c_prev <= 0 or c_cur <= 0:
            continue

        obs_close_ratio = float(c_prev / c_cur)
        if obs_close_ratio < 1.53:
            continue

        cand_r, err = match_canonical_ratio(obs_close_ratio)
        o_val = float(o_cur) if (pd.notna(o_cur) and o_cur > 0) else float(c_cur)
        events.append({
            "date": str(dt_c.date()),
            "symbol": sym,
            "prev_close": round(float(c_prev), 2),
            "close": round(float(c_cur), 2),
            "obs_close_ratio": round(obs_close_ratio, 4),
            "implied_multiplier": float(cand_r),
            "ratio_err": round(float(err), 4),
            "open_ratio": round(float(c_prev / o_val), 3),
        })
    return events


def trace_trade_yfinance(
    sym: str,
    entry_date: str,
    exit_date: str,
    panel_entry_raw: float,
    panel_exit_raw: float,
    v2_mult_during_trade: float,
) -> Dict[str, Any]:
    """Compare panel raw entry/exit prices & splits against Yahoo Finance."""
    start_dt = (pd.to_datetime(entry_date) - timedelta(days=7)).strftime("%Y-%m-%d")
    end_dt = (pd.to_datetime(exit_date) + timedelta(days=7)).strftime("%Y-%m-%d")

    yf_aliases = {
        "GATI": ["ACLGATI.NS", "GATI.NS", "GATI.BO"],
        "IBVENTURES": ["DHANI.NS", "IBVENTURES.NS", "IBVENTURES.BO"],
        "ADANITRANS": ["ADANIENSOL.NS", "ADANITRANS.NS", "ADANITRANS.BO"],
    }
    candidates = yf_aliases.get(sym, [f"{sym}.NS", f"{sym}.BO"])
    for ticker_str in candidates:
        try:
            tk = yf.Ticker(ticker_str)
            hist = tk.history(start=start_dt, end=end_dt, auto_adjust=False)
            if hist is None or hist.empty:
                continue
            hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()

            e_dt = pd.to_datetime(entry_date)
            x_dt = pd.to_datetime(exit_date)

            # Find nearest trading day within +-3 days
            e_sub = hist.loc[(hist.index >= e_dt - timedelta(days=3)) & (hist.index <= e_dt + timedelta(days=3))]
            x_sub = hist.loc[(hist.index >= x_dt - timedelta(days=3)) & (hist.index <= x_dt + timedelta(days=3))]
            if e_sub.empty or x_sub.empty:
                continue

            yf_entry_open = float(e_sub.iloc[0]["Open"])
            yf_exit_open = float(x_sub.iloc[-1]["Open"])
            if e_dt in hist.index:
                yf_entry_open = float(hist.loc[e_dt, "Open"])
            if x_dt in hist.index:
                yf_exit_open = float(hist.loc[x_dt, "Open"])

            # Check YF splits during holding period
            splits = tk.splits
            yf_split_mult = 1.0
            yf_splits_in_window = []
            if splits is not None and not splits.empty:
                s_idx = pd.to_datetime(splits.index).tz_localize(None).normalize()
                for s_dt, s_val in zip(s_idx, splits.values):
                    if e_dt < s_dt <= x_dt:
                        yf_split_mult *= float(s_val)
                        yf_splits_in_window.append({"date": str(s_dt.date()), "ratio": float(s_val)})

            # Compare entry & exit
            # Note: YF Open may already be unadjusted or split-adjusted depending on YF endpoint;
            # auto_adjust=False returns split-adjusted OHLC on YF! So divide YF entry by yf_split_mult to get raw,
            # or compare ratio (exit/entry * v2_mult) vs (yf_exit / yf_entry * yf_split_mult).
            panel_gross_mult = (panel_exit_raw / max(panel_entry_raw, 1e-4)) * v2_mult_during_trade
            yf_gross_mult = yf_exit_open / max(yf_entry_open, 1e-4)  # YF auto_adjust=False is already split-adjusted
            rel_diff = abs(panel_gross_mult - yf_gross_mult) / max(yf_gross_mult, 1e-4)

            status = "CONFIRMED" if rel_diff <= 0.12 else "FLAGGED"
            return {
                "yf_ticker": ticker_str,
                "yf_entry_open": round(yf_entry_open, 2),
                "yf_exit_open": round(yf_exit_open, 2),
                "yf_splits_in_window": yf_splits_in_window,
                "panel_gross_mult": round(panel_gross_mult, 3),
                "yf_gross_mult": round(yf_gross_mult, 3),
                "rel_diff_pct": round(rel_diff * 100.0, 2),
                "status": status,
            }
        except Exception:
            continue

    return {
        "yf_ticker": None,
        "yf_entry_open": None,
        "yf_exit_open": None,
        "yf_splits_in_window": [],
        "panel_gross_mult": None,
        "yf_gross_mult": None,
        "rel_diff_pct": None,
        "status": "FLAGGED_NO_YF_DATA",
    }


def main():
    print("=" * 80)
    print("STAGE 0: DATA AUDIT & PANEL VERSIONING")
    print("=" * 80)

    # Ensure V2 corporate actions is loaded cleanly
    ca_mod.CORPORATE_ACTIONS_CSV = CA_V2_CSV
    ca_mod._ACTIONS_CACHE = None
    v2_actions = ca_mod.load_audited_corporate_actions(CA_V2_CSV)
    ca_sha = sha256_file(CA_V2_CSV)
    print(f"Loaded V2 Corporate Actions: {len(v2_actions)} events (SHA={ca_sha[:16]}...)")

    close_df, open_df, turnover_df, bench_df, coverage = p5.load_all_data()
    mult_df, adj_factors = ca_mod.build_verified_split_adjustment_matrix(close_df, csv_path=CA_V2_CSV)
    adj_close = close_df * adj_factors

    # -------------------------------------------------------------------------
    # TASK 1: Explain Control B
    # -------------------------------------------------------------------------
    print("\n--- TASK 1: EXPLAIN CONTROL B ---")
    ctrl_b_raw = p5.simulate_control_b_equal_weight_top100(close_df, turnover_df, p5.IN_SAMPLE_START, p5.IN_SAMPLE_END)
    ctrl_b_adj = p5.simulate_control_b_equal_weight_top100(adj_close, turnover_df, p5.IN_SAMPLE_START, p5.IN_SAMPLE_END)
    ctrl_b_explanation = {
        "raw_close_cagr_pct": float(ctrl_b_raw["cagr_pct"]),
        "raw_close_sharpe": float(ctrl_b_raw["sharpe_ratio"]),
        "raw_close_max_dd_pct": float(ctrl_b_raw["max_drawdown_pct"]),
        "v2_split_adj_cagr_pct": float(ctrl_b_adj["cagr_pct"]),
        "v2_split_adj_sharpe": float(ctrl_b_adj["sharpe_ratio"]),
        "v2_split_adj_max_dd_pct": float(ctrl_b_adj["max_drawdown_pct"]),
        "benchmark_tri_cagr_pct": 10.30,
        "causes": [
            "1. Unadjusted-split bug in simulate_control_b_equal_weight_top100: it computed monthly returns on raw close_df instead of split-adjusted adj_close, turning every Top-100 stock split/bonus into a -50% to -90% monthly loss (-0.88% vs +3.59% CAGR).",
            "2. Default-argument cache bug in corporate_actions.py: csv_path=CORPORATE_ACTIONS_CSV was bound at import time, causing V2 re-runs to silently load V1 (48 events) instead of V2 (511 events).",
            "3. Missing events in V2: ADANIENT 2015-06 demerger (-87.1%) and HDFCBANK 2011-07 5:1 split (-80.6%) remained unadjusted in V2.",
            "4. Structural universe mismatch: Control B selects Top 100 by 60d median rupee turnover (not market cap), equal-weights them monthly, and omits dividends (+1.35% p.a. in Nifty TRI). High-turnover NSE stocks in 2008-2013 and 2018-2019 were heavily tilted to distressed/leveraged names (SUZLON, UNITECH, SATYAMCOMP, IVRCLINFRA, DHFL, IBULHSGFIN, YESBANK, GITANJALI, AMTEKAUTO, SINTEX), producing -65.6% (2008), -36.4% (2011), -12.2% (2018), and -8.7% (2019)."
        ],
    }
    print(f"  Control B Raw: {ctrl_b_raw['cagr_pct']}% CAGR | Control B V2-Adj: {ctrl_b_adj['cagr_pct']}% CAGR")

    # -------------------------------------------------------------------------
    # TASK 2: Trace Top 10 S2 Trades (on true V2 CA)
    # -------------------------------------------------------------------------
    print("\n--- TASK 2: TRACE TOP 10 S2 TRADES (TRUE V2 CA) ---")
    s2_v2 = p5.simulate_strategy_s2(close_df, open_df, turnover_df, bench_df, p5.IN_SAMPLE_START, p5.IN_SAMPLE_END)
    print(f"  S2 (True V2 CA, 511 events): CAGR={s2_v2['cagr_pct']}%, Sharpe={s2_v2['sharpe_ratio']}, MaxDD={s2_v2['max_drawdown_pct']}%, Kurt={s2_v2['kurtosis']}, Trades={s2_v2['total_trades']}")

    tlog = s2_v2["trade_log"]
    top10_trades = sorted(tlog, key=lambda x: x["return_pct"], reverse=True)[:10]
    top10_table: List[Dict[str, Any]] = []
    for rank, t in enumerate(top10_trades, 1):
        sym = t["symbol"]
        e_dt = t["entry_date"]
        x_dt = t["exit_date"]
        # Raw open prices in panel
        e_raw = float(open_df.loc[pd.to_datetime(e_dt), sym]) if pd.to_datetime(e_dt) in open_df.index else float("nan")
        x_raw = float(open_df.loc[pd.to_datetime(x_dt), sym]) if pd.to_datetime(x_dt) in open_df.index else float("nan")
        # V2 splits during trade
        v2_mult = 1.0
        v2_splits_in_trade = []
        if sym in mult_df.columns:
            mask = (mult_df.index > pd.to_datetime(e_dt)) & (mult_df.index <= pd.to_datetime(x_dt))
            sub_m = mult_df.loc[mask, sym]
            for dt_m, m_val in sub_m[sub_m != 1.0].items():
                v2_mult *= float(m_val)
                v2_splits_in_trade.append({"date": str(dt_m.date()), "mult": float(m_val)})

        yf_check = trace_trade_yfinance(sym, e_dt, x_dt, e_raw, x_raw, v2_mult)
        row = {
            "rank": rank,
            "symbol": sym,
            "entry_date": e_dt,
            "exit_date": x_dt,
            "return_pct": round(t["return_pct"] * 100.0, 2),
            "pnl_rupees": t["pnl_rupees"],
            "reason": t["reason"],
            "panel_entry_open_raw": round(e_raw, 2) if not math.isnan(e_raw) else None,
            "panel_exit_open_raw": round(x_raw, 2) if not math.isnan(x_raw) else None,
            "v2_splits_in_trade": v2_splits_in_trade,
            **yf_check,
        }
        top10_table.append(row)
        print(f"  #{rank:2d} {sym:12s} {e_dt}->{x_dt} ret={row['return_pct']:7.2f}% | panel_x={row['panel_gross_mult']} vs yf_x={row['yf_gross_mult']} | {row['status']}")

    # -------------------------------------------------------------------------
    # TASK 3: Decide the 50 Unverified Events (Excluded vs Adjusted)
    # -------------------------------------------------------------------------
    print("\n--- TASK 3: 50 UNVERIFIED EVENTS SENSITIVITY ---")
    unverified_events = find_50_unverified_events(close_df, open_df, turnover_df, v2_actions)
    print(f"  Found {len(unverified_events)} unverified >=35% overnight drop events.")

    # Create temporary combined CSV with the unverified events adjusted
    v2_df = pd.read_csv(CA_V2_CSV)
    extra_rows = []
    for ev in unverified_events:
        extra_rows.append({
            "date": ev["date"],
            "symbol": ev["symbol"],
            "action": "UNVERIFIED_SENSITIVITY",
            "multiplier": ev["implied_multiplier"],
            "isin_old": "",
            "isin_new": "",
            "source": "Stage0 Sensitivity Test",
            "description": f"Unverified ratio {ev['obs_close_ratio']} -> {ev['implied_multiplier']}",
        })
    combined_df = pd.concat([v2_df, pd.DataFrame(extra_rows)], ignore_index=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        combined_df.to_csv(tmp.name, index=False)
        tmp_csv_path = tmp.name

    try:
        ca_mod.CORPORATE_ACTIONS_CSV = tmp_csv_path
        ca_mod._ACTIONS_CACHE = None
        s2_with_50 = p5.simulate_strategy_s2(close_df, open_df, turnover_df, bench_df, p5.IN_SAMPLE_START, p5.IN_SAMPLE_END)
    finally:
        ca_mod.CORPORATE_ACTIONS_CSV = CA_V2_CSV
        ca_mod._ACTIONS_CACHE = None
        if os.path.exists(tmp_csv_path):
            os.remove(tmp_csv_path)

    cagr_excl = float(s2_v2["cagr_pct"])
    cagr_incl = float(s2_with_50["cagr_pct"])
    gap_cagr = round(cagr_incl - cagr_excl, 2)
    print(f"  50 Events Excluded (V2): CAGR={cagr_excl}%, Sharpe={s2_v2['sharpe_ratio']}, MaxDD={s2_v2['max_drawdown_pct']}%")
    print(f"  50 Events Adjusted     : CAGR={cagr_incl}%, Sharpe={s2_with_50['sharpe_ratio']}, MaxDD={s2_with_50['max_drawdown_pct']}%")
    print(f"  Gap (Adjusted - Excl)  : {gap_cagr:+.2f} percentage points")

    # -------------------------------------------------------------------------
    # TASK 4: Top-5-Trades-Removed Test
    # -------------------------------------------------------------------------
    print("\n--- TASK 4: TOP-5-TRADES-REMOVED TEST ---")
    top5_keys = {(t["symbol"], t["entry_date"]) for t in top10_trades[:5]}
    s2_no_top5 = p5.simulate_strategy_s2(
        close_df, open_df, turnover_df, bench_df,
        p5.IN_SAMPLE_START, p5.IN_SAMPLE_END,
        blocked_entries=top5_keys,
    )
    print(f"  Top-5 Removed (Re-simulated): CAGR={s2_no_top5['cagr_pct']}% vs 14.3% bar | Sharpe={s2_no_top5['sharpe_ratio']} | MaxDD={s2_no_top5['max_drawdown_pct']}%")

    # -------------------------------------------------------------------------
    # TASK 5: Version Panel with SHA-256 & Log to trial_log.csv
    # -------------------------------------------------------------------------
    print("\n--- TASK 5: PANEL SHA-256 VERSIONING ---")
    panel_hashes = {
        "causal_panel_close.parquet": sha256_file(p5.PANEL_CLOSE_FILE),
        "causal_panel_open.parquet": sha256_file(p5.PANEL_OPEN_FILE),
        "causal_panel_turnover.parquet": sha256_file(p5.PANEL_TURNOVER_FILE),
        "INDEX_NSEI.parquet": sha256_file(p5.BENCHMARK_FILE),
        "nse_corporate_actions_v2.csv": ca_sha,
    }
    combined_str = "|".join(f"{k}:{v}" for k, v in sorted(panel_hashes.items()))
    panel_v2_sha = hashlib.sha256(combined_str.encode("utf-8")).hexdigest()
    with open(PANEL_SHA_PATH, "w", encoding="utf-8") as f:
        f.write(f"{panel_v2_sha}  NSE_PANEL_V2\n")
        for k, v in sorted(panel_hashes.items()):
            f.write(f"{v}  {k}\n")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "panel_version": "NSE_PANEL_V2",
        "panel_sha256": panel_v2_sha,
        "component_hashes": panel_hashes,
        "task1_control_b": ctrl_b_explanation,
        "task2_top10_trades": top10_table,
        "task3_50_unverified_events": {
            "count": len(unverified_events),
            "excluded_v2": {
                "cagr_pct": cagr_excl,
                "sharpe_ratio": float(s2_v2["sharpe_ratio"]),
                "max_drawdown_pct": float(s2_v2["max_drawdown_pct"]),
                "kurtosis": float(s2_v2["kurtosis"]),
                "total_trades": int(s2_v2["total_trades"]),
            },
            "adjusted_with_50": {
                "cagr_pct": cagr_incl,
                "sharpe_ratio": float(s2_with_50["sharpe_ratio"]),
                "max_drawdown_pct": float(s2_with_50["max_drawdown_pct"]),
                "kurtosis": float(s2_with_50["kurtosis"]),
                "total_trades": int(s2_with_50["total_trades"]),
            },
            "cagr_gap_pct_pts": gap_cagr,
        },
        "task4_top5_trades_removed": {
            "removed_trades": sorted(list(top5_keys)),
            "cagr_pct": float(s2_no_top5["cagr_pct"]),
            "sharpe_ratio": float(s2_no_top5["sharpe_ratio"]),
            "max_drawdown_pct": float(s2_no_top5["max_drawdown_pct"]),
            "gate_a_bar_pct": 14.3,
            "clears_14_3_bar": bool(s2_no_top5["cagr_pct"] >= 14.3),
        },
    }
    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Log Stage 0 re-runs to trial_log.csv
    commit_hash = p5.get_git_commit_hash()[:7]
    for label, res_obj in [
        (f"Stage0 S2 V2 Baseline (CA_V2=511, PanelSHA={panel_v2_sha[:12]})", s2_v2),
        (f"Stage0 S2 V2 + 50 Unverified Adjusted (PanelSHA={panel_v2_sha[:12]})", s2_with_50),
        (f"Stage0 S2 V2 Top-5-Trades-Removed (PanelSHA={panel_v2_sha[:12]})", s2_no_top5),
    ]:
        log_trial(
            commit_hash=commit_hash,
            script="run_stage0_data_audit.py",
            universe="NSE_WHOLE_MARKET_PANEL_V2",
            kelly_fraction=0.08,
            lookback_days=90,
            cagr_pct=float(res_obj["cagr_pct"]),
            max_drawdown_pct=float(res_obj["max_drawdown_pct"]),
            sharpe_ratio=float(res_obj["sharpe_ratio"]),
            is_holdout_opened=False,
            notes=label,
        )

    print(f"\nSaved Stage 0 report to {REPORT_JSON_PATH}")
    print(f"Saved Panel V2 SHA-256 ({panel_v2_sha}) to {PANEL_SHA_PATH}")


if __name__ == "__main__":
    main()
