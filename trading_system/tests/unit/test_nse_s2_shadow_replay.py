import os
import pandas as pd
import numpy as np

from trading_system.scripts.run_nse_s2_shadow_replay import (
    FIDELITY_COLUMNS,
    compute_signal_match_rate,
    evaluate_weekly_fidelity,
)


def _make_price_df(dates, start_price=100.0, drift=0.002):
    vals = [start_price * ((1.0 + drift) ** i) for i in range(len(dates))]
    return pd.DataFrame(
        {
            "open": vals,
            "high": [v * 1.01 for v in vals],
            "low": [v * 0.99 for v in vals],
            "close": vals,
            "volume": [1_000_000.0] * len(dates),
        },
        index=dates,
    )


def test_signal_match_rate_exact_and_mismatch():
    sh = pd.DataFrame([
        {"date": "2026-11-25", "symbol": "AAA.NS", "action": "BUY"},
        {"date": "2026-11-26", "symbol": "BBB.NS", "action": "SELL"},
    ])
    rp_same = sh.copy()
    assert compute_signal_match_rate(sh, rp_same) == 100.0

    rp_diff = pd.DataFrame([
        {"date": "2026-11-25", "symbol": "AAA.NS", "action": "BUY"},
        {"date": "2026-11-26", "symbol": "CCC.NS", "action": "BUY"},
    ])
    # 1 match out of 3 union keys = 33.33%
    assert compute_signal_match_rate(sh, rp_diff) == 33.33


def test_evaluate_weekly_fidelity_appends_row(tmp_path):
    dates = pd.bdate_range("2025-09-01", periods=310)
    shadow_dates = [str(d.date()) for d in dates[-5:]]

    eq_path = tmp_path / "shadow_eq.csv"
    tr_path = tmp_path / "shadow_tr.csv"
    fid_path = tmp_path / "fidelity.csv"

    pd.DataFrame([{"date": d, "nav": 80000.0} for d in shadow_dates]).to_csv(eq_path, index=False)
    pd.DataFrame(columns=["date", "symbol", "action", "shares", "fill_price"]).to_csv(tr_path, index=False)

    bench_df = _make_price_df(dates, start_price=24000.0, drift=0.0002)
    universe_data = {"TESTSTOCK.NS": _make_price_df(dates, start_price=100.0, drift=0.0001)}

    res = evaluate_weekly_fidelity(
        equity_log_path=str(eq_path),
        trades_csv_path=str(tr_path),
        fidelity_csv_path=str(fid_path),
        universe_data=universe_data,
        bench_df=bench_df,
    )
    assert res["status"] == "REPLAYED"
    assert os.path.exists(fid_path)
    out_df = pd.read_csv(fid_path)
    assert list(out_df.columns) == FIDELITY_COLUMNS
    assert len(out_df) == 1
    assert out_df.iloc[0]["fidelity_passed"] == True
