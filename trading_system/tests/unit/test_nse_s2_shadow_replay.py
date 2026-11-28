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


def test_evaluate_weekly_fidelity_handles_production_session_date_schema(tmp_path):
    """Regression guard: real nse_s2_shadow CSVs use `session_date` and `timestamp`, not `date`."""
    dates = pd.bdate_range("2025-09-01", periods=310)
    shadow_dates = [str(d.date()) for d in dates[-2:]]

    eq_path = tmp_path / "nse_s2_shadow_equity_log.csv"
    tr_path = tmp_path / "nse_s2_shadow_trades.csv"
    fid_path = tmp_path / "nse_s2_shadow_fidelity.csv"

    # Production schema: wall-clock `date` differs from market-bar `session_date`, and trades use `timestamp` + `session_date`
    pd.DataFrame([
        {"date": "2026-11-26 19:59:40", "session_date": shadow_dates[0], "nav": 80018.5},
        {"date": "2026-11-27 19:48:42", "session_date": shadow_dates[1], "nav": 80213.08},
    ]).to_csv(eq_path, index=False)

    bench_df = _make_price_df(dates, start_price=24000.0, drift=0.0002)
    universe_data = {"TESTSTOCK.NS": _make_price_df(dates, start_price=100.0, drift=0.002)}

    # Capture what the replay runner actually trades on those 2 session dates, then verify production CSV schema matches
    from trading_system.scripts.run_nse_s2_shadow import NSES2ShadowRunner
    runner = NSES2ShadowRunner(
        state_file=str(tmp_path / "st.json"),
        trades_file=str(tr_path),
        equity_log_file=str(eq_path),
    )
    runner.run_daily_cycle(universe_data={k: v.loc[:dates[-2]] for k, v in universe_data.items()}, bench_df=bench_df.loc[:dates[-2]])
    runner.run_daily_cycle(universe_data=universe_data, bench_df=bench_df)

    res = evaluate_weekly_fidelity(
        equity_log_path=str(eq_path),
        trades_csv_path=str(tr_path),
        fidelity_csv_path=str(fid_path),
        universe_data=universe_data,
        bench_df=bench_df,
    )
    assert res["status"] == "REPLAYED"
    assert res["signal_match_rate_pct"] == 100.0
    assert res["equity_gap_pct"] < 0.05
    assert res["fidelity_passed"] is True
