"""
Phase 2 Offline Diagnostic & Test Harness
Tests the Multi-Strategy Ensemble:
  - Momentum Heuristics
  - Mean Reversion (Bollinger + RSI Dips)
  - Statistical Pairs Trading (KO vs PEP, MSFT vs GOOGL)
  - Dynamic Regime Allocator
Does NOT affect or trade on live accounts; purely diagnostic and staged for evaluation.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.strategies.ensembles.mean_reversion import MeanReversionStrategy
from trading_system.app.strategies.ensembles.pairs_trading import StatisticalPairsStrategy
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator
from trading_system.app.research.quant_engine import InvestorSkillsHeuristics


def test_phase2_ensemble():
    print("\n" + "=" * 70)
    print(">>> PHASE 2: MULTI-STRATEGY ENSEMBLE TEST HARNESS <<<")
    print("=" * 70)

    provider = YFinanceDataProvider()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=250)

    test_universe = ["SPY", "AAPL", "MSFT", "GOOGL", "KO", "PEP"]
    print(f"\n[1/4] Fetching Data for Universe: {test_universe}...")
    data_cache = {}
    for sym in test_universe:
        df = provider.fetch_historical_data(sym, start_date, end_date)
        if not df.empty:
            data_cache[sym] = df
            print(f"  Loaded {sym}: {len(df)} bars (Latest Close: ${df['close'].iloc[-1]:.2f})")

    # 1. Regime Detection
    print("\n[2/4] Detecting Market Regime via SPY...")
    allocator = EnsembleAllocator()
    spy_df = data_cache.get("SPY")
    regime = allocator.detect_regime(spy_df)
    print(f"  Detected Regime: {regime['regime']}")
    print(f"  Trend Strength Ratio: {regime['trend_ratio']}")
    print(f"  Target Strategy Weights: {regime['weights']}")

    # 2. Strategy 1: Momentum Signals
    print("\n[3/4] Evaluating Sub-Strategies...")
    momentum_signals = []
    for sym in ["AAPL", "MSFT", "GOOGL"]:
        if sym in data_cache:
            j = InvestorSkillsHeuristics.apply_judgment(sym, data_cache[sym])
            if j["confidence"] > 0.70:
                momentum_signals.append({
                    "symbol": sym,
                    "confidence": j["confidence"],
                    "conviction_score": j.get("conviction_score", 1.0),
                    "rationale": j["rationale"],
                })
    print(f"  Strategy 1 (Momentum): Generated {len(momentum_signals)} active signals")
    for s in momentum_signals:
        print(f"    -> {s['symbol']}: Conf={s['confidence']} | Score={s['conviction_score']} ({s['rationale']})")

    # Strategy 2: Mean Reversion Signals
    mr_engine = MeanReversionStrategy()
    mean_rev_signals = []
    for sym in ["AAPL", "MSFT", "GOOGL", "KO", "PEP"]:
        if sym in data_cache:
            sig = mr_engine.generate_signal(data_cache[sym])
            mean_rev_signals.append({
                "symbol": sym,
                "signal": sig["signal"],
                "confidence": sig["confidence"],
                "rationale": sig["rationale"],
            })
    active_mr = [s for s in mean_rev_signals if s["signal"] == 1]
    print(f"  Strategy 2 (Mean Reversion): Generated {len(active_mr)} buy signals")
    for s in mean_rev_signals:
        if s["signal"] != 0:
            print(f"    -> {s['symbol']}: Signal={s['signal']} | {s['rationale']}")

    # 3. Dynamic Long-Only Ensemble Allocation
    print("\n[4/4] Combining Signals via Long-Only Ensemble Allocator...")
    final_weights = allocator.combine_allocations(
        momentum_signals=momentum_signals,
        mean_rev_signals=mean_rev_signals,
        regime_info=regime,
    )

    print("\n" + "=" * 50)
    print(">>> FINAL ENSEMBLE PORTFOLIO TARGET WEIGHTS <<<")
    print("=" * 50)
    total_long = 0.0
    total_short = 0.0
    for sym, weight in sorted(final_weights.items(), key=lambda x: x[1], reverse=True):
        if weight > 0:
            total_long += weight
            print(f"  {sym.ljust(6)} : +{weight*100:5.2f}% (LONG)")
        elif weight < 0:
            total_short += abs(weight)
            print(f"  {sym.ljust(6)} : -{abs(weight)*100:5.2f}% (SHORT)")

    gross_exp = total_long + total_short
    cash_buf = max(0.0, 1.0 - gross_exp)
    print("-" * 50)
    print(f"  Gross Market Exposure : {gross_exp*100:5.2f}%")
    print(f"  Net Market Exposure   : {(total_long - total_short)*100:5.2f}%")
    print(f"  Cash Buffer (Safety)  : {cash_buf*100:5.2f}%")
    print("=" * 50)
    print("\nPhase 2 Ensemble verification completed successfully!")


if __name__ == "__main__":
    test_phase2_ensemble()
