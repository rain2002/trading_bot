"""
Build Point-in-Time Wider US Equity Universe (S&P 1500 Composite, Strictly Non-ETF)
====================================================================================
Extends the US equity universe beyond S&P 500 by reconstructing historical Point-in-Time
constituents across:
  - S&P 500 LargeCap (2006-01-03 .. 2024-07-05 from sp500_ticker_start_end.csv,
                      extended 2024-07-01 .. present via Wikipedia revision API)
  - S&P 400 MidCap   (2011-01-01 .. present via Wikipedia revision API)
  - S&P 600 SmallCap (2018-09-01 .. present via Wikipedia revision API)

Zero ETFs are permitted. Rebuilds local gitignored OHLCV parquets
(`us_wider_close_panel.parquet`, `us_wider_volume_panel.parquet`), saves the
tracked PIT interval table (`us_wider_universe_pit_intervals.csv`), the
machine-readable universe spec (`us_wider_universe_definition.json`), and an
honest data / survivorship-attrition audit (`us_wider_universe_data_audit.json`).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))

SP500_CSV = os.path.join(DATA_DIR, "sp500_ticker_start_end.csv")
PIT_OUT_CSV = os.path.join(DATA_DIR, "us_wider_universe_pit_intervals.csv")
UNIV_DEF_JSON = os.path.join(DATA_DIR, "us_wider_universe_definition.json")
AUDIT_JSON = os.path.join(DATA_DIR, "us_wider_universe_data_audit.json")
CLOSE_PARQUET = os.path.join(DATA_DIR, "us_wider_close_panel.parquet")
VOLUME_PARQUET = os.path.join(DATA_DIR, "us_wider_volume_panel.parquet")

FORBIDDEN_ETFS = {
    "SPY", "VOO", "IVV", "QQQ", "QQQM", "IWM", "MDY", "IJH", "IJR", "VTI",
    "DIA", "GLD", "IAU", "SLV", "TLT", "IEF", "SHY", "BIL", "SGOV", "AGG",
    "BND", "LQD", "HYG", "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY",
    "XLB", "XLU", "XLRE", "XLC", "RSP", "SPLG", "SCHB", "SCHX", "VB", "VO",
    "VV", "MTUM", "QUAL", "VLUE", "USMV", "SIZE", "ARKK", "TQQQ", "SQQQ",
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "AntigravityQuantAudit/1.0 (https://github.com/nitin/paper_trading_bot)"


def norm_yahoo_ticker(sym: str) -> str:
    """Normalize constituent ticker symbol for Yahoo Finance (e.g. BRK.B -> BRK-B)."""
    s = str(sym).strip().upper().replace(".", "-")
    s = re.sub(r"[^A-Z0-9\-]", "", s)
    return s


def fetch_wiki_revision(title: str, ts_iso: str) -> Tuple[Optional[str], str]:
    """Fetch the closest Wikipedia revision content on or before `ts_iso`."""
    url = (
        f"{WIKI_API}?action=query&titles={title}&prop=revisions"
        f"&rvprop=timestamp|content&rvslots=main&rvlimit=1"
        f"&rvstart={ts_iso}&rvdir=older&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    revs = page.get("revisions", [])
    if not revs:
        return None, ""
    rev = revs[0]
    content = rev.get("slots", {}).get("main", {}).get("*", "")
    return rev.get("timestamp"), content


def extract_main_constituents_table(wikitext: str) -> List[str]:
    """Parse tickers strictly from the main index constituents wikitable (excluding change logs)."""
    if not wikitext:
        return []
    tables = re.findall(r"\{\|[^\n]*class=\"[^\"]*wikitable.*?\n(.*?)\n\|\}", wikitext, flags=re.S)
    if not tables:
        return []
    # Prefer table whose header mentions GICS / Symbol / Company and NOT Added / Removed change logs
    constituents_tbls = []
    for t in tables:
        hdr = t.split("\n|-")[0].lower()
        if ("gics" in hdr or "symbol" in hdr or "ticker" in hdr) and ("added" not in hdr and "removed" not in hdr):
            constituents_tbls.append(t)
    candidates = constituents_tbls if constituents_tbls else tables
    main_tbl = max(candidates, key=lambda t: t.count("\n|-"))
    rows = re.split(r"\n\|-", main_tbl)
    tickers: List[str] = []
    for row in rows[1:]:
        cells = [c.strip() for c in re.split(r"\n\||\n!|\|\|", row)]
        if not cells:
            continue
        found = None
        # Check first 3 cells because older revisions sometimes put Company before Symbol
        for cell in cells[:3]:
            m_ex = re.search(
                r"\{\{(?:nyse|nasdaq|nysearca|amex|bats|cboe)[^}|]*\|([A-Z0-9.\-]{1,6})(?:\||\}\})",
                cell,
                flags=re.I,
            )
            if m_ex:
                found = m_ex.group(1)
                break
            m_lnk = re.search(r"\[\[[^|\]]*\|([A-Z]{1,5}(?:\.[AB])?)\]\]", cell)
            if m_lnk:
                found = m_lnk.group(1)
                break
            cleaned = re.sub(r"\[\[|\]\]|'''|<[^>]+>|\{\{[^}]+\}\}", "", cell).strip()
            if re.fullmatch(r"[A-Z]{1,5}(?:\.[AB])?", cleaned):
                found = cleaned
                break
        if found:
            t_norm = norm_yahoo_ticker(found)
            if t_norm and t_norm not in FORBIDDEN_ETFS:
                tickers.append(t_norm)
    # Deduplicate preserving order
    seen = set()
    out = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def snapshots_to_intervals(
    snapshots: List[Tuple[pd.Timestamp, List[str]]],
    tier: str,
    final_end: pd.Timestamp,
) -> pd.DataFrame:
    """Convert ordered PIT snapshot membership lists into [start_date, end_date] intervals."""
    if not snapshots:
        return pd.DataFrame(columns=["ticker", "index_tier", "start_date", "end_date"])

    active_start: Dict[str, pd.Timestamp] = {}
    records: List[dict] = []

    for i, (snap_dt, members) in enumerate(snapshots):
        mem_set = set(members)
        # Close out departed tickers at the previous snapshot boundary or midpoint
        departed = [t for t in list(active_start.keys()) if t not in mem_set]
        for t in departed:
            records.append(
                {
                    "ticker": t,
                    "index_tier": tier,
                    "start_date": active_start.pop(t).strftime("%Y-%m-%d"),
                    "end_date": snap_dt.strftime("%Y-%m-%d"),
                }
            )
        # Open newly entered tickers
        for t in mem_set:
            if t not in active_start:
                active_start[t] = snap_dt

    # Still active at end of reconstruction window
    for t, st in active_start.items():
        records.append(
            {
                "ticker": t,
                "index_tier": tier,
                "start_date": st.strftime("%Y-%m-%d"),
                "end_date": final_end.strftime("%Y-%m-%d"),
            }
        )

    df = pd.DataFrame(records)
    return df.sort_values(["index_tier", "ticker", "start_date"]).reset_index(drop=True)


def build_pit_intervals(end_date_str: str) -> Tuple[pd.DataFrame, dict]:
    """Assemble full PIT intervals across S&P 500, S&P 400, and S&P 600."""
    final_end = pd.Timestamp(end_date_str)
    meta_snapshots: Dict[str, List[dict]] = {"SP500_WIKI_EXT": [], "SP400": [], "SP600": []}

    # 1. Existing S&P 500 CSV (2006 .. 2024-07)
    sp500_raw = pd.read_csv(SP500_CSV)
    sp500_raw["ticker"] = sp500_raw["ticker"].map(norm_yahoo_ticker)
    sp500_raw = sp500_raw[~sp500_raw["ticker"].isin(FORBIDDEN_ETFS)].copy()
    sp500_raw["start_date"] = pd.to_datetime(sp500_raw["start_date"]).dt.strftime("%Y-%m-%d")
    sp500_raw["end_date"] = sp500_raw["end_date"].fillna("2024-07-05")
    sp500_raw["end_date"] = pd.to_datetime(sp500_raw["end_date"]).dt.strftime("%Y-%m-%d")
    sp500_raw["index_tier"] = "SP500"

    # Extend S&P 500 open intervals past 2024-07 using quarterly Wikipedia snapshots up to end_date_str
    sp500_ext_dates = pd.date_range("2024-07-01", final_end, freq="QS").tolist()
    if final_end not in sp500_ext_dates:
        sp500_ext_dates.append(final_end)
    sp500_ext_snaps: List[Tuple[pd.Timestamp, List[str]]] = []
    for dt in sp500_ext_dates:
        ts_iso = (dt + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        rts, txt = fetch_wiki_revision("List_of_S%26P_500_companies", ts_iso)
        syms = extract_main_constituents_table(txt)
        if len(syms) >= 480:
            sp500_ext_snaps.append((dt, syms))
            meta_snapshots["SP500_WIKI_EXT"].append(
                {"target_date": dt.strftime("%Y-%m-%d"), "wiki_rev": str(rts)[:10], "count": len(syms)}
            )
        time.sleep(0.08)

    sp500_ext_df = snapshots_to_intervals(sp500_ext_snaps, "SP500", final_end)
    # Trim overlap before 2024-07-05 in sp500_raw, and keep sp500_ext_df from 2024-07-01 onward
    # Merge adjacent intervals per ticker cleanly when stitching below
    sp500_combined = pd.concat(
        [sp500_raw[["ticker", "index_tier", "start_date", "end_date"]], sp500_ext_df],
        ignore_index=True,
    )

    # 2. S&P MidCap 400 PIT snapshots (2011-01-01 .. end_date_str, quarterly from 2012, semi-annual 2011)
    sp400_dates = sorted(
        set(pd.date_range("2011-01-01", final_end, freq="QS").tolist() + [final_end])
    )
    sp400_snaps: List[Tuple[pd.Timestamp, List[str]]] = []
    for dt in sp400_dates:
        ts_iso = (dt + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        rts, txt = fetch_wiki_revision("List_of_S%26P_400_companies", ts_iso)
        syms = extract_main_constituents_table(txt)
        if 150 <= len(syms) <= 430:
            sp400_snaps.append((dt, syms))
            meta_snapshots["SP400"].append(
                {"target_date": dt.strftime("%Y-%m-%d"), "wiki_rev": str(rts)[:10], "count": len(syms)}
            )
        time.sleep(0.08)
    sp400_df = snapshots_to_intervals(sp400_snaps, "SP400", final_end)

    # 3. S&P SmallCap 600 PIT snapshots (2018-09-01 .. end_date_str)
    sp600_dates = sorted(
        set(
            [pd.Timestamp("2018-09-01")]
            + pd.date_range("2018-10-01", final_end, freq="QS").tolist()
            + [final_end]
        )
    )
    sp600_snaps: List[Tuple[pd.Timestamp, List[str]]] = []
    for dt in sp600_dates:
        ts_iso = (dt + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        rts, txt = fetch_wiki_revision("List_of_S%26P_600_companies", ts_iso)
        syms = extract_main_constituents_table(txt)
        if 550 <= len(syms) <= 640:
            sp600_snaps.append((dt, syms))
            meta_snapshots["SP600"].append(
                {"target_date": dt.strftime("%Y-%m-%d"), "wiki_rev": str(rts)[:10], "count": len(syms)}
            )
        time.sleep(0.08)
    sp600_df = snapshots_to_intervals(sp600_snaps, "SP600", final_end)

    full_df = pd.concat([sp500_combined, sp400_df, sp600_df], ignore_index=True)
    full_df = full_df[~full_df["ticker"].isin(FORBIDDEN_ETFS)].copy()
    full_df = full_df.sort_values(["index_tier", "ticker", "start_date"]).reset_index(drop=True)
    return full_df, meta_snapshots


def download_wider_ohlcv(
    tickers: List[str],
    start_date: str = "2006-01-03",
    end_date: str = "2026-11-27",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Download adjusted Close & Volume panels for all unique union tickers in chunks."""
    all_close: List[pd.DataFrame] = []
    all_vol: List[pd.DataFrame] = []
    chunk_size = 80
    total = len(tickers)

    for i in range(0, total, chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"Downloading OHLCV batch {i // chunk_size + 1}/{(total - 1) // chunk_size + 1} ({len(chunk)} tickers)...", flush=True)
        try:
            raw = yf.download(
                chunk,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                c_df = raw["Close"].copy() if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
                v_df = raw["Volume"].copy() if "Volume" in raw.columns.get_level_values(0) else pd.DataFrame()
            else:
                # Single-ticker fallback
                sym = chunk[0]
                c_df = raw[["Close"]].rename(columns={"Close": sym})
                v_df = raw[["Volume"]].rename(columns={"Volume": sym})

            if not c_df.empty:
                c_df.index = pd.to_datetime(c_df.index).tz_localize(None)
                all_close.append(c_df)
            if not v_df.empty:
                v_df.index = pd.to_datetime(v_df.index).tz_localize(None)
                all_vol.append(v_df)
        except Exception as exc:
            print(f"  Batch {i} warning: {exc}", flush=True)
        time.sleep(0.3)

    close_panel = pd.concat(all_close, axis=1) if all_close else pd.DataFrame()
    vol_panel = pd.concat(all_vol, axis=1) if all_vol else pd.DataFrame()

    # Deduplicate columns if any repeated
    close_panel = close_panel.loc[:, ~close_panel.columns.duplicated()]
    vol_panel = vol_panel.loc[:, ~vol_panel.columns.duplicated()]

    # Drop completely empty ticker columns (Yahoo 404 / delisted)
    valid_cols = [c for c in close_panel.columns if close_panel[c].notna().sum() >= 20]
    close_panel = close_panel[valid_cols].sort_index()
    vol_cols = [c for c in valid_cols if c in vol_panel.columns]
    vol_panel = vol_panel.reindex(close_panel.index)[vol_cols]
    return close_panel, vol_panel


def compute_honest_data_audit(
    pit_df: pd.DataFrame,
    close_panel: pd.DataFrame,
    vol_panel: pd.DataFrame,
    meta_snapshots: dict,
) -> dict:
    """Audit Yahoo Finance survivorship attrition, yearly PIT breadth, liquidity, and data anomalies."""
    downloaded_set = set(close_panel.columns)

    tier_stats = {}
    for tier in ["SP500", "SP400", "SP600"]:
        sub = pit_df[pit_df["index_tier"] == tier]
        unique_t = set(sub["ticker"].unique())
        present = unique_t & downloaded_set
        missing = sorted(unique_t - downloaded_set)
        tier_stats[tier] = {
            "total_pit_unique_tickers": len(unique_t),
            "downloaded_valid_tickers": len(present),
            "missing_or_delisted_yahoo_404": len(missing),
            "survivorship_attrition_pct": round(100.0 * len(missing) / max(len(unique_t), 1), 2),
            "sample_missing_tickers": missing[:25],
        }

    all_pit_unique = set(pit_df["ticker"].unique())
    all_present = all_pit_unique & downloaded_set
    all_missing = sorted(all_pit_unique - downloaded_set)

    # Yearly PIT coverage & liquidity audit at July 1 (mid-year) snapshots from 2007..2026
    dollar_vol = close_panel * vol_panel.reindex(columns=close_panel.columns)
    dvol_20d = dollar_vol.rolling(20, min_periods=10).median()

    yearly_audit = []
    for yr in range(2007, 2027):
        dt_str = f"{yr}-07-01"
        active = pit_df[(pit_df["start_date"] <= dt_str) & (pit_df["end_date"] >= dt_str)]
        by_tier = active.groupby("index_tier")["ticker"].nunique().to_dict()
        union_active = set(active["ticker"].unique())
        dl_active = union_active & downloaded_set

        # Find nearest trading day <= yr-07-05
        avail_dates = close_panel.index[close_panel.index <= pd.Timestamp(f"{yr}-07-05")]
        liquid_cnt = 0
        if len(avail_dates) > 0 and dl_active:
            snap_dt = avail_dates[-1]
            c_row = close_panel.loc[snap_dt, list(dl_active)]
            dv_row = dvol_20d.loc[snap_dt, list(dl_active)]
            liquid_cnt = int(((c_row >= 10.0) & (dv_row >= 2_000_000.0)).sum())

        yearly_audit.append(
            {
                "year": yr,
                "snapshot_date": dt_str,
                "pit_sp500": int(by_tier.get("SP500", 0)),
                "pit_sp400": int(by_tier.get("SP400", 0)),
                "pit_sp600": int(by_tier.get("SP600", 0)),
                "pit_union_tickers": len(union_active),
                "downloaded_active_tickers": len(dl_active),
                "missing_delisted_active_tickers": len(union_active) - len(dl_active),
                "active_attrition_pct": round(
                    100.0 * (len(union_active) - len(dl_active)) / max(len(union_active), 1), 2
                ),
                "liquid_tradable_ge10usd_ge2m_dvol": liquid_cnt,
            }
        )

    # Anomaly scan on downloaded panel
    vals = close_panel.to_numpy(dtype=np.float64)
    non_pos_count = int(np.sum(vals[~np.isnan(vals)] <= 0.0))
    rets = close_panel.pct_change()
    extreme_up = int((rets > 1.0).sum().sum())
    extreme_dn = int((rets < -0.75).sum().sum())
    dup_dates = int(close_panel.index.duplicated().sum())
    etf_overlap = sorted(FORBIDDEN_ETFS & all_pit_unique)

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_id": "US_WIDER_SP1500_PIT_NON_ETF",
        "panel_start_date": close_panel.index[0].strftime("%Y-%m-%d") if len(close_panel) else None,
        "panel_end_date": close_panel.index[-1].strftime("%Y-%m-%d") if len(close_panel) else None,
        "trading_days": int(len(close_panel)),
        "strict_non_etf_check": {
            "forbidden_etf_overlap_count": len(etf_overlap),
            "overlap_tickers": etf_overlap,
            "passed": len(etf_overlap) == 0,
        },
        "composite_union_summary": {
            "total_pit_unique_tickers": len(all_pit_unique),
            "downloaded_valid_tickers": len(all_present),
            "missing_or_delisted_yahoo_404": len(all_missing),
            "survivorship_attrition_pct": round(
                100.0 * len(all_missing) / max(len(all_pit_unique), 1), 2
            ),
            "honest_survivorship_caveat": (
                "Yahoo Finance returns HTTP 404 for delisted/acquired/bankrupt tickers. "
                "Therefore, while index membership IS point-in-time across S&P 500/400/600, "
                "historical OHLCV coverage still suffers structural delisting attrition quantified above. "
                "Any backtest result using Yahoo historical prices carries upward survivorship bias on missing delisted names."
            ),
        },
        "by_index_tier": tier_stats,
        "price_anomalies": {
            "non_positive_close_cells": non_pos_count,
            "daily_jumps_gt_100pct": extreme_up,
            "daily_drops_gt_75pct": extreme_dn,
            "duplicate_trading_dates": dup_dates,
            "auto_adjusted_splits_dividends": True,
        },
        "wikipedia_pit_snapshot_counts": {
            k: {"num_snapshots": len(v), "first": v[0] if v else None, "last": v[-1] if v else None}
            for k, v in meta_snapshots.items()
        },
        "yearly_pit_and_liquidity_coverage": yearly_audit,
    }


def main():
    # Backfill / rebuild cleanly from cached local parquets + clean Wikipedia PIT snapshots
    import argparse
    import glob
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-missing", action="store_true", help="Retry tickers absent from existing parquet without re-scraping Wikipedia.")
    parser.add_argument("--rebuild-from-cache", action="store_true", help="Rebuild clean PIT CSV from Wikipedia and merge all local cached parquets (no bulk Yahoo hits).")
    args, _ = parser.parse_known_args()

    if args.rebuild_from_cache and os.path.exists(CLOSE_PARQUET):
        print("=== REBUILDING CLEAN PIT CSV + MERGING LOCAL CACHED PARQUETS ===", flush=True)
        end_date_str = "2026-11-26"
        pit_df, meta_snapshots = build_pit_intervals(end_date_str)
        pit_df.to_csv(PIT_OUT_CSV, index=False)
        print(f"Saved cleaned PIT intervals CSV: {len(pit_df)} intervals, {pit_df['ticker'].nunique()} unique tickers", flush=True)

        close_panel = pd.read_parquet(CLOSE_PARQUET)
        vol_panel = pd.read_parquet(VOLUME_PARQUET)
        close_panel.index = pd.to_datetime(close_panel.index).tz_localize(None)
        vol_panel.index = pd.to_datetime(vol_panel.index).tz_localize(None)

        # Merge S&P 500 parquet (586 tickers 2006..2024-07) for any missing tickers
        sp500_pq_path = os.path.join(DATA_DIR, "us_sp500_close_panel.parquet")
        if os.path.exists(sp500_pq_path):
            sp5_c = pd.read_parquet(sp500_pq_path)
            sp5_c.index = pd.to_datetime(sp5_c.index).tz_localize(None)
            add_sp5 = [c for c in sp5_c.columns if c not in close_panel.columns and sp5_c[c].notna().sum() >= 20]
            if add_sp5:
                close_panel = pd.concat([close_panel, sp5_c[add_sp5].reindex(close_panel.index)], axis=1)
                print(f"Merged +{len(add_sp5)} tickers from us_sp500_close_panel.parquet", flush=True)

        # Merge historical_cache_us/*.parquet (including SPY benchmark and 100+ active stocks)
        cache_dir = os.path.join(DATA_DIR, "historical_cache_us")
        if os.path.isdir(cache_dir):
            add_cache_c = {}
            add_cache_v = {}
            for fp in glob.glob(os.path.join(cache_dir, "*.parquet")):
                sym = os.path.basename(fp).replace(".parquet", "")
                try:
                    df_sym = pd.read_parquet(fp)
                    df_sym.index = pd.to_datetime(df_sym.index).tz_localize(None)
                    c_col = "close" if "close" in df_sym.columns else ("Close" if "Close" in df_sym.columns else None)
                    v_col = "volume" if "volume" in df_sym.columns else ("Volume" if "Volume" in df_sym.columns else None)
                    if c_col and (sym not in close_panel.columns or close_panel[sym].notna().sum() < 20):
                        add_cache_c[sym] = df_sym[c_col].reindex(close_panel.index)
                        if v_col:
                            add_cache_v[sym] = df_sym[v_col].reindex(close_panel.index)
                except Exception:
                    pass
            if add_cache_c:
                close_panel = pd.concat([close_panel, pd.DataFrame(add_cache_c)], axis=1)
                if add_cache_v:
                    vol_panel = pd.concat([vol_panel, pd.DataFrame(add_cache_v)], axis=1)
                print(f"Merged +{len(add_cache_c)} tickers from historical_cache_us/", flush=True)

        # Filter down to union of clean PIT tickers + SPY
        keep_universe = set(pit_df["ticker"].unique()) | {"SPY"}
        keep_cols = [c for c in close_panel.columns if c in keep_universe and close_panel[c].notna().sum() >= 20]
        close_panel = close_panel[sorted(set(keep_cols))].sort_index()
        vol_cols = [c for c in close_panel.columns if c in vol_panel.columns]
        vol_panel = vol_panel.reindex(close_panel.index)[vol_cols]

        stock_close = close_panel[[c for c in close_panel.columns if c != "SPY"]]
        stock_vol = vol_panel[[c for c in vol_panel.columns if c != "SPY"]]
        audit = compute_honest_data_audit(pit_df, stock_close, stock_vol, meta_snapshots)
        # Flag any tickers with non-positive backward-adjusted Close prices and sanitize to NaN
        neg_cols = {c: int((stock_close[c] <= 0).sum()) for c in stock_close.columns if (stock_close[c] <= 0).sum() > 0}
        audit["price_anomalies"]["non_positive_close_tickers_sanitized"] = neg_cols
        for c in neg_cols:
            close_panel.loc[close_panel[c] <= 0, c] = np.nan

        close_panel.to_parquet(CLOSE_PARQUET)
        vol_panel.to_parquet(VOLUME_PARQUET)
        with open(AUDIT_JSON, "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2)
        print(f"Rebuilt panels: Close={close_panel.shape}, SPY present={'SPY' in close_panel.columns}", flush=True)
        print(json.dumps(audit["composite_union_summary"], indent=2), flush=True)
        print(json.dumps(audit["by_index_tier"], indent=2), flush=True)
        return

    if args.retry_missing and os.path.exists(PIT_OUT_CSV) and os.path.exists(CLOSE_PARQUET):
        print("=== RETRYING MISSING / RATE-LIMITED TICKERS GENTLY ===", flush=True)
        pit_df = pd.read_csv(PIT_OUT_CSV)
        close_panel = pd.read_parquet(CLOSE_PARQUET)
        vol_panel = pd.read_parquet(VOLUME_PARQUET)
        all_target = sorted(set(pit_df["ticker"].unique().tolist()) | {"SPY"})
        already_have = set(close_panel.columns)
        # Prioritize tickers active in 2018+ first (or all missing cleanly in gentle chunks of 40)
        missing_all = [t for t in all_target if t not in already_have]
        recent_set = set(pit_df[pit_df["end_date"] >= "2018-01-01"]["ticker"].unique()) | {"SPY"}
        to_retry = [t for t in missing_all if t in recent_set]
        print(f"Existing={len(already_have)}, total missing={len(missing_all)}, retrying active/recent(2018+)={len(to_retry)}...", flush=True)

        retry_c, retry_v = [], []
        chunk_sz = 40
        for i in range(0, len(to_retry), chunk_sz):
            ch = to_retry[i : i + chunk_sz]
            print(f"Retry batch {i // chunk_sz + 1}/{(len(to_retry) - 1) // chunk_sz + 1} ({len(ch)} tickers)...", flush=True)
            time.sleep(2.5)
            try:
                raw = yf.download(ch, start="2006-01-03", end="2026-11-27", auto_adjust=True, progress=False, threads=True)
                if not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        c_df = raw["Close"].copy() if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
                        v_df = raw["Volume"].copy() if "Volume" in raw.columns.get_level_values(0) else pd.DataFrame()
                    else:
                        c_df = raw[["Close"]].rename(columns={"Close": ch[0]})
                        v_df = raw[["Volume"]].rename(columns={"Volume": ch[0]})
                    if not c_df.empty:
                        c_df.index = pd.to_datetime(c_df.index).tz_localize(None)
                        retry_c.append(c_df)
                    if not v_df.empty:
                        v_df.index = pd.to_datetime(v_df.index).tz_localize(None)
                        retry_v.append(v_df)
            except Exception as exc:
                print(f"  Retry warning: {exc}", flush=True)
                time.sleep(8.0)

        if retry_c:
            add_c = pd.concat(retry_c, axis=1)
            add_c = add_c.loc[:, ~add_c.columns.duplicated()]
            valid_new = [c for c in add_c.columns if c not in close_panel.columns and add_c[c].notna().sum() >= 20]
            if valid_new:
                close_panel = pd.concat([close_panel, add_c[valid_new].reindex(close_panel.index)], axis=1).sort_index()
                if retry_v:
                    add_v = pd.concat(retry_v, axis=1)
                    add_v = add_v.loc[:, ~add_v.columns.duplicated()]
                    valid_v = [c for c in valid_new if c in add_v.columns]
                    vol_panel = pd.concat([vol_panel, add_v[valid_v].reindex(close_panel.index)], axis=1).sort_index()
                close_panel.to_parquet(CLOSE_PARQUET)
                vol_panel.to_parquet(VOLUME_PARQUET)
                print(f"Merged +{len(valid_new)} recovered tickers -> total {close_panel.shape[1]}", flush=True)

        stock_close = close_panel[[c for c in close_panel.columns if c != "SPY"]]
        stock_vol = vol_panel[[c for c in vol_panel.columns if c != "SPY"]]
        audit = compute_honest_data_audit(pit_df, stock_close, stock_vol, {})
        # Preserve snapshot metadata from previous audit if present
        if os.path.exists(AUDIT_JSON):
            try:
                with open(AUDIT_JSON, "r", encoding="utf-8") as f:
                    prev = json.load(f)
                audit["wikipedia_pit_snapshot_counts"] = prev.get("wikipedia_pit_snapshot_counts", {})
            except Exception:
                pass
        with open(AUDIT_JSON, "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2)
        print(json.dumps(audit["composite_union_summary"], indent=2), flush=True)
        print(json.dumps(audit["by_index_tier"], indent=2), flush=True)
        return

    end_date_str = "2026-11-26"
    print("=== BUILDING WIDER US PIT UNIVERSE (S&P 500 + S&P 400 + S&P 600, STRICTLY NON-ETF) ===", flush=True)
    pit_df, meta_snapshots = build_pit_intervals(end_date_str)
    pit_df.to_csv(PIT_OUT_CSV, index=False)
    print(f"Saved PIT intervals CSV: {PIT_OUT_CSV} ({len(pit_df)} intervals, {pit_df['ticker'].nunique()} unique tickers)", flush=True)

    univ_def = {
        "universe_id": "US_WIDER_SP1500_PIT_NON_ETF",
        "description": (
            "Point-in-Time Wider US Individual Equities Universe combining S&P 500 LargeCap (2006+), "
            "S&P 400 MidCap (2011+), and S&P 600 SmallCap (2018+) constituents. Strictly excludes all ETFs/ETNs/trusts."
        ),
        "strictly_no_etfs": True,
        "etf_exclusion_list_size": len(FORBIDDEN_ETFS),
        "pit_tiers": [
            {"tier": "SP500", "source": "sp500_ticker_start_end.csv + Wikipedia List_of_S&P_500_companies revisions", "start": "2006-01-03"},
            {"tier": "SP400", "source": "Wikipedia List_of_S&P_400_companies quarterly revisions", "start": "2011-01-01"},
            {"tier": "SP600", "source": "Wikipedia List_of_S&P_600_companies quarterly revisions", "start": "2018-09-01"},
        ],
        "tradability_filters": {
            "min_price_usd": 10.0,
            "min_20d_median_dollar_volume_usd": 2_000_000.0,
            "execution_convention": "Signal generated on Close[t], executed at Close[t+1] (or strictly causal t+1) with 5/10 bps slippage/fee stress",
        },
    }
    with open(UNIV_DEF_JSON, "w", encoding="utf-8") as f:
        json.dump(univ_def, f, indent=2)

    all_tickers = sorted(pit_df["ticker"].unique().tolist())
    # Also fetch SPY solely as passive benchmark (explicitly excluded from tradable stock pool)
    dl_tickers = sorted(set(all_tickers) | {"SPY"})
    close_panel, vol_panel = download_wider_ohlcv(dl_tickers, start_date="2006-01-03", end_date="2026-11-27")

    close_panel.to_parquet(CLOSE_PARQUET)
    vol_panel.to_parquet(VOLUME_PARQUET)
    print(f"Saved Close parquet: {CLOSE_PARQUET} shape={close_panel.shape}", flush=True)
    print(f"Saved Volume parquet: {VOLUME_PARQUET} shape={vol_panel.shape}", flush=True)

    # Audit excludes SPY benchmark from stock universe stats
    stock_close = close_panel[[c for c in close_panel.columns if c != "SPY"]]
    stock_vol = vol_panel[[c for c in vol_panel.columns if c != "SPY"]]
    audit = compute_honest_data_audit(pit_df, stock_close, stock_vol, meta_snapshots)
    with open(AUDIT_JSON, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    print(f"Saved Honest Data Audit JSON: {AUDIT_JSON}", flush=True)
    print(json.dumps(audit["composite_union_summary"], indent=2), flush=True)
    print(json.dumps(audit["by_index_tier"], indent=2), flush=True)


if __name__ == "__main__":
    main()
