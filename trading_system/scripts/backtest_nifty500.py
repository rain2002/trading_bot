"""
Audited Backtest for the ENTIRE Market: Nifty 500 (Broad Market: Large, Mid, Small Caps)
========================================================================================
Runs the 17-Year (2007-2024) backtest across all 474 active NSE equities with:
- Volatility Radar (Daniel & Moskowitz panic filter + Barroso & Santa-Clara inverse-vol scaling)
- Full statutory costs: STT (10 bps buy & sell), turnover charges, GST, stamp duty, DP charges (Rs 14.75/sale)
- 15% Short-Term Capital Gains (STCG) tax
- Sourced liquid yield compounding on idle cash
"""

import os
import sys
import json
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import trading_system.scripts.backtest_growth_stock_momentum as bgm

bgm.CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache_nifty500")

def run_nifty500_backtest():
    print("=" * 80)
    print("RUNNING 17-YEAR BACKTEST ON THE ENTIRE NIFTY 500 (LARGE + MID + SMALL CAPS)")
    print("=" * 80, flush=True)

    bench_df, macro_bull, precalc, timeline = bgm.load_market_data(
        start_date="2007-09-17",
        end_date="2024-12-31"
    )

    print("Computing Baselines...", flush=True)
    baselines = bgm.compute_baselines(bench_df, precalc, timeline)

    variants = [
        (1, "Wide-Trend Runner (20 Slots)"),
        (2, "Asymmetric Multi-Bagger (10 Slots)"),
        (3, "Breakout Compounder (15 Slots)")
    ]

    results = []

    for v, name in variants:
        print(f"\n>>> Running Variant {v}: {name} with Volatility Radar ON...", flush=True)
        t0 = time.time()
        res_radar_on = bgm.run_simulation(
            bench_df, macro_bull, precalc, timeline,
            variant=v, slippage_bps=bgm.DEFAULT_SLIPPAGE_BPS,
            label=f"Variant {v} Radar ON",
            use_vol_radar=True
        )
        print(f"    Completed in {time.time()-t0:.1f}s | Post-Tax CAGR: {res_radar_on['cagr_pct']:.2f}% | Max DD: {res_radar_on['max_drawdown_pct']:.2f}% | Calmar: {res_radar_on['calmar_ratio']:.2f}")

        print(f">>> Running Variant {v}: {name} with Volatility Radar OFF...", flush=True)
        t0 = time.time()
        res_radar_off = bgm.run_simulation(
            bench_df, macro_bull, precalc, timeline,
            variant=v, slippage_bps=bgm.DEFAULT_SLIPPAGE_BPS,
            label=f"Variant {v} Radar OFF",
            use_vol_radar=False
        )
        print(f"    Completed in {time.time()-t0:.1f}s | Post-Tax CAGR: {res_radar_off['cagr_pct']:.2f}% | Max DD: {res_radar_off['max_drawdown_pct']:.2f}% | Calmar: {res_radar_off['calmar_ratio']:.2f}")

        results.append({
            "variant": v,
            "name": name,
            "radar_on": res_radar_on,
            "radar_off": res_radar_off
        })

    # Summary table
    print("\n" + "=" * 80)
    print("FINAL AUDITED SCOREBOARD: ENTIRE NIFTY 500 (2007-2024, POST-TAX & ALL FEES)")
    print("=" * 80)
    print(f"{'Strategy / Variant':<38} | {'Post-Tax CAGR':<14} | {'Max Drawdown':<14} | {'Calmar':<8}")
    print("-" * 80)
    for r in results:
        v = r["variant"]
        name = r["name"]
        ron = r["radar_on"]
        roff = r["radar_off"]
        print(f"{name + ' (Radar ON)':<38} | {ron['cagr_pct']:>12.2f}% | {ron['max_drawdown_pct']:>12.2f}% | {ron['calmar_ratio']:>6.2f}")
        print(f"{name + ' (Radar OFF)':<38} | {roff['cagr_pct']:>12.2f}% | {roff['max_drawdown_pct']:>12.2f}% | {roff['calmar_ratio']:>6.2f}")
    print("-" * 80)
    b1 = baselines["b1_tri"]
    b3 = baselines["b3_trend"]
    print(f"{'Passive Baseline: Nifty 50 TRI':<38} | {b1['cagr_pct']:>12.2f}% | {b1['max_drawdown_pct']:>12.2f}% | {b1['calmar_ratio']:>6.2f}")
    print(f"{'Passive Baseline: 200-SMA Trend':<38} | {b3['cagr_pct']:>12.2f}% | {b3['max_drawdown_pct']:>12.2f}% | {b3['calmar_ratio']:>6.2f}")
    print("=" * 80)

    # Save to JSON
    out_file = os.path.join(PROJECT_ROOT, "trading_system", "data", "backtest_results_nifty500_broad_market.json")
    save_payload = {
        "universe": "NIFTY_500_BROAD_MARKET",
        "ticker_count": len(precalc),
        "period": "2007-09-17 to 2024-12-31",
        "variants": [
            {
                "variant": r["variant"],
                "name": r["name"],
                "radar_on": {k: v for k, v in r["radar_on"].items() if k not in ["equity_curve", "trade_log"]},
                "radar_off": {k: v for k, v in r["radar_off"].items() if k not in ["equity_curve", "trade_log"]}
            }
            for r in results
        ],
        "baselines": baselines
    }
    with open(out_file, "w") as f:
        json.dump(save_payload, f, indent=2)
    print(f"\nResults successfully saved to {out_file}")

if __name__ == "__main__":
    run_nifty500_backtest()
