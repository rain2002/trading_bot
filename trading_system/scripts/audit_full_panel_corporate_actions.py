"""
Full-Panel NSE Corporate Actions Audit & Versioned Generator (V2)
=================================================================
Audits all liquid non-ETF NSE equities across 2007-2024 (causal_panel_close.parquet)
for unadjusted stock splits and bonus issues without adjusting genuine market crashes.

Verification Hierarchy:
1. Authoritative V1 circulars from nse_corporate_actions_audited.csv (preserved 100%).
2. Primary yfinance official corporate-action `.splits` feed for active NSE tickers,
   aligned to exact Bhavcopy ex-date within +/- 2 trading sessions.
3. Conservative Bhavcopy microstructure check ONLY for delisted/renamed tickers where
   Yahoo Finance returns empty/404: requires exact opening-gap match (within 8%)
   to a canonical NSE split/bonus ratio AND proportional volume-share expansion,
   and skips penny stocks or multi-day crash cascades.

Outputs:
- trading_system/data/nse_corporate_actions_v2.csv
- trading_system/data/nse_corporate_actions_v2.sha256
- trading_system/data/nse_full_panel_ca_audit.json
"""

import os
import sys
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.data.corporate_actions import is_etf_ticker

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
PANEL_CLOSE_FILE = os.path.join(DATA_DIR, "causal_panel_close.parquet")
PANEL_OPEN_FILE = os.path.join(DATA_DIR, "causal_panel_open.parquet")
PANEL_TURNOVER_FILE = os.path.join(DATA_DIR, "causal_panel_turnover.parquet")
CA_V1_CSV = os.path.join(DATA_DIR, "nse_corporate_actions_audited.csv")

CA_V2_CSV = os.path.join(DATA_DIR, "nse_corporate_actions_v2.csv")
CA_V2_SHA = os.path.join(DATA_DIR, "nse_corporate_actions_v2.sha256")
AUDIT_JSON = os.path.join(DATA_DIR, "nse_full_panel_ca_audit.json")

CANONICAL_RATIOS = [1.2, 1.25, 1.3333333333333333, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 10.0, 20.0]

KNOWN_CRASH_BLACKLIST = {
    "SATYAMCOMP", "COREPROTEC", "YESBANK", "DHFL", "PCJEWELLER", "VAKRANGEE",
    "KWALITY", "MANPASAND", "JETAIRWAYS", "SUZLON_CRASH", "RPOWER_CRASH",
    "UNITECH", "GVK_CRASH", "8KMILES", "RELCAPITAL", "RELINFRA", "RCOM",
    "ZEEL", "INDIABULLS", "GTL", "GTLINFRA", "HCC", "SINTEX", "JPASSOCIAT_CRASH",
}


def fetch_yf_splits(sym: str) -> Tuple[str, List[Tuple[str, float]], bool]:
    """Fetch official split/bonus history from Yahoo Finance for SYM.NS."""
    try:
        sp = yf.Ticker(f"{sym}.NS").splits
        if sp is None or len(sp) == 0:
            return sym, [], False
        out = []
        for dt, val in sp.items():
            dt_str = pd.to_datetime(dt).strftime("%Y-%m-%d")
            fval = float(val)
            if "2007-01-01" <= dt_str <= "2024-12-31" and fval > 1.05:
                out.append((dt_str, fval))
        return sym, out, True
    except Exception:
        return sym, [], False


def match_canonical_ratio(val: float) -> Tuple[float, float]:
    """Return nearest canonical NSE split/bonus ratio and relative error."""
    best_r = min(CANONICAL_RATIOS, key=lambda r: abs(val - r) / r)
    rel_err = abs(val - best_r) / best_r
    return best_r, rel_err


def main():
    print("=" * 85)
    print("FULL-PANEL NSE CORPORATE ACTIONS AUDIT (3,232 EQUITIES, 2007-2024)")
    print("=" * 85)

    close_df = pd.read_parquet(PANEL_CLOSE_FILE)
    open_df = pd.read_parquet(PANEL_OPEN_FILE)
    turnover_df = pd.read_parquet(PANEL_TURNOVER_FILE)

    valid_cols = [c for c in close_df.columns if not is_etf_ticker(c) and c in open_df.columns and c in turnover_df.columns]
    close_df = close_df[valid_cols].sort_index()
    open_df = open_df[valid_cols].reindex(close_df.index)
    turnover_df = turnover_df[valid_cols].reindex(close_df.index)

    med_to = turnover_df.rolling(60, min_periods=5).median()
    qty_df = turnover_df / close_df.replace(0.0, np.nan)
    med_qty = qty_df.rolling(20, min_periods=5).median()

    prev_c = close_df.shift(1)
    prev_to = med_to.shift(1)
    ret_df = (close_df / prev_c) - 1.0

    # Identify all liquid S2-eligible drops <= -20%
    liq_drop_mask = (prev_c >= 20.0) & (prev_to >= 20000000.0) & (ret_df <= -0.20)
    hits = liq_drop_mask.stack()
    drop_events = [(dt, sym) for dt, sym in hits[hits].index]
    unique_syms = sorted(list({sym for _, sym in drop_events}))
    print(f"Found {len(drop_events)} liquid drops (<= -20%) across {len(unique_syms)} unique equities.")

    # Load V1 audited circulars
    v1_df = pd.read_csv(CA_V1_CSV)
    v1_df["date"] = pd.to_datetime(v1_df["date"]).dt.strftime("%Y-%m-%d")
    v1_df["symbol"] = v1_df["symbol"].str.strip().str.upper()

    audited_records: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, row in v1_df.iterrows():
        key = (row["date"], row["symbol"])
        audited_records[key] = {
            "date": row["date"],
            "symbol": row["symbol"],
            "action": str(row.get("action", "SPLIT_OR_BONUS")),
            "multiplier": float(row["multiplier"]),
            "isin_old": str(row.get("isin_old", "")),
            "isin_new": str(row.get("isin_new", "")),
            "source": str(row.get("source", "NSE Circular (V1)")),
            "description": str(row.get("description", "")),
        }
    print(f"Loaded {len(audited_records)} V1 authoritative events from {os.path.basename(CA_V1_CSV)}.")

    # Fetch Yahoo Finance official split/bonus history in parallel
    print(f"Querying Yahoo Finance official splits across {len(unique_syms)} NSE tickers...")
    yf_splits_map: Dict[str, List[Tuple[str, float]]] = {}
    yf_found_syms = set()
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch_yf_splits, s) for s in unique_syms]
        for fut in as_completed(futs):
            sym, sp_list, has_data = fut.result()
            if has_data:
                yf_found_syms.add(sym)
                yf_splits_map[sym] = sp_list

    print(f"Yahoo Finance returned official split records for {len(yf_found_syms)}/{len(unique_syms)} tickers.")

    dates_list = close_df.index.tolist()
    date_pos = {d: i for i, d in enumerate(dates_list)}

    yf_added = 0
    bhav_added = 0
    rejected_crashes = []

    # 1. Align Yahoo official splits to exact Bhavcopy drop date (+/- 2 trading days)
    for sym, sp_list in sorted(yf_splits_map.items()):
        if sym not in close_df.columns:
            continue
        s_close = close_df[sym]
        for yf_dt_str, yf_mult in sp_list:
            # Skip if V1 already covers within +/- 3 calendar days
            yf_ts = pd.to_datetime(yf_dt_str)
            already_v1 = any(
                s == sym and abs((pd.to_datetime(d) - yf_ts).days) <= 4
                for d, s in audited_records.keys()
            )
            if already_v1:
                continue

            # Find Bhavcopy index nearest to yf_ts
            pos = close_df.index.searchsorted(yf_ts)
            cand_positions = [p for p in range(max(1, pos - 2), min(len(dates_list), pos + 3))]
            best_dt = None
            best_mult = yf_mult
            best_score = 999.0
            for p in cand_positions:
                dt_c = dates_list[p]
                c_prev = s_close.iloc[p - 1]
                o_cur = open_df[sym].iloc[p]
                c_cur = s_close.iloc[p]
                if pd.isna(c_prev) or pd.isna(c_cur) or c_cur <= 0 or c_prev <= 0:
                    continue
                obs_close = float(c_prev / c_cur)
                obs_open = float(c_prev / o_cur) if (pd.notna(o_cur) and o_cur > 0) else obs_close
                if max(obs_close, obs_open) < 1.12:
                    continue
                err_c = abs(obs_close - yf_mult) / yf_mult
                err_o = abs(obs_open - yf_mult) / yf_mult
                err_min = min(err_c, err_o)
                chosen_mult = yf_mult
                # Catch combined split+bonus on exact ex-date (where Yahoo recorded only 1 leg, e.g. 10x+2x=20x)
                if err_min >= 0.35:
                    cand_r, cand_err = match_canonical_ratio(obs_open)
                    if cand_err <= 0.08 and cand_r > yf_mult:
                        err_min = cand_err
                        chosen_mult = cand_r
                if err_min < 0.35 and err_min < best_score:
                    best_score = err_min
                    best_mult = chosen_mult
                    best_dt = dt_c

            if best_dt is not None:
                dt_str = str(best_dt.date())
                audited_records[(dt_str, sym)] = {
                    "date": dt_str,
                    "symbol": sym,
                    "action": "SPLIT_OR_BONUS",
                    "multiplier": round(best_mult, 6),
                    "isin_old": "",
                    "isin_new": "",
                    "source": f"Yahoo Finance Official Splits (ex_ref={yf_dt_str}, yf={yf_mult:g})",
                    "description": f"Verified split/bonus multiplier {best_mult:.4f} (ex-date aligned error={best_score*100:.1f}%)",
                }
                yf_added += 1

    # 2. For tickers with NO Yahoo split history (delisted/renamed or >= 40% extreme splits),
    # apply conservative Bhavcopy open-gap + share-volume verification (only for severe >= 45% drops)
    for dt_c, sym in drop_events:
        dt_str = str(dt_c.date())
        # Skip if already handled within +/- 4 days
        if any(s == sym and abs((pd.to_datetime(d) - dt_c).days) <= 4 for d, s in audited_records.keys()):
            continue

        p = date_pos[dt_c]
        if p < 5 or p >= len(dates_list) - 1:
            continue

        c_prev = close_df[sym].iloc[p - 1]
        o_cur = open_df[sym].iloc[p]
        c_cur = close_df[sym].iloc[p]
        q_cur = qty_df[sym].iloc[p]
        q_med = med_qty[sym].iloc[p - 1]

        if any(pd.isna(x) or x <= 0 for x in (c_prev, o_cur, c_cur)):
            continue

        obs_open_ratio = float(c_prev / o_cur)
        obs_close_ratio = float(c_prev / c_cur)
        vol_mult = float(q_cur / q_med) if (pd.notna(q_med) and q_med > 0 and pd.notna(q_cur)) else 0.0

        # Check multi-day cascade guard (real crashes often gap down repeatedly; splits happen cleanly once)
        prev3_ret = float((c_prev / close_df[sym].iloc[max(0, p - 4)]) - 1.0) if pd.notna(close_df[sym].iloc[max(0, p - 4)]) else 0.0
        next3_c = close_df[sym].iloc[min(len(dates_list) - 1, p + 3)]
        next3_ret = float((next3_c / c_cur) - 1.0) if pd.notna(next3_c) else 0.0

        cand_r, open_err = match_canonical_ratio(obs_open_ratio)
        _, close_err = match_canonical_ratio(obs_close_ratio)

        # Strict Bhavcopy microstructure acceptance ONLY for unmapped/delisted tickers with clean >=2x split signatures
        is_yf_missing = sym not in yf_found_syms
        if (
            is_yf_missing
            and sym not in KNOWN_CRASH_BLACKLIST
            and cand_r >= 2.0
            and open_err <= 0.06
            and close_err <= 0.14
            and vol_mult >= max(1.4, 0.35 * cand_r)
            and prev3_ret > -0.25
            and abs(next3_ret) < 0.25
        ):
            audited_records[(dt_str, sym)] = {
                "date": dt_str,
                "symbol": sym,
                "action": "SPLIT_OR_BONUS",
                "multiplier": round(cand_r, 6),
                "isin_old": "",
                "isin_new": "",
                "source": "Bhavcopy Open+Volume Microstructure Verified (Delisted/Renamed)",
                "description": f"Open ratio {obs_open_ratio:.3f} vs {cand_r:.2f} (err={open_err*100:.1f}%, vol_x={vol_mult:.1f}x)",
            }
            bhav_added += 1
        elif obs_close_ratio >= 1.53:  # >= 35% drop rejected as crash / unverified
            rejected_crashes.append({
                "date": dt_str,
                "symbol": sym,
                "prev_close": round(float(c_prev), 2),
                "close": round(float(c_cur), 2),
                "raw_drop_pct": round((1.0 / obs_close_ratio - 1.0) * 100.0, 1),
                "open_ratio": round(obs_open_ratio, 3),
                "vol_mult": round(vol_mult, 2),
                "yf_has_splits": not is_yf_missing,
            })

    out_rows = sorted(audited_records.values(), key=lambda x: (x["date"], x["symbol"]))
    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(CA_V2_CSV, index=False)

    csv_bytes = open(CA_V2_CSV, "rb").read()
    ca_sha = hashlib.sha256(csv_bytes).hexdigest()
    with open(CA_V2_SHA, "w", encoding="utf-8") as f:
        f.write(ca_sha + "\n")

    summary = {
        "v1_events": len(v1_df),
        "yf_verified_added": yf_added,
        "bhavcopy_delisted_verified_added": bhav_added,
        "total_v2_audited_events": len(out_df),
        "rejected_unverified_or_crashes_gt35pct": len(rejected_crashes),
        "v2_csv_sha256": ca_sha,
        "sample_yf_added": [r for r in out_rows if "Yahoo Finance" in r["source"]][:15],
        "sample_bhav_added": [r for r in out_rows if "Bhavcopy" in r["source"]][:15],
        "sample_rejected_crashes": rejected_crashes[:20],
    }
    with open(AUDIT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nAUDIT COMPLETE:")
    print(f"  V1 Circulars Preserved         : {len(v1_df)}")
    print(f"  Yahoo Finance Official Added   : {yf_added}")
    print(f"  Bhavcopy Delisted Verified     : {bhav_added}")
    print(f"  Total V2 Audited Events        : {len(out_df)}")
    print(f"  Rejected Crashes / Unverified  : {len(rejected_crashes)}")
    print(f"  Versioned CSV                  : {CA_V2_CSV}")
    print(f"  SHA-256 Seal                   : {ca_sha}")


if __name__ == "__main__":
    main()
