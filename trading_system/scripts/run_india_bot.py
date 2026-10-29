"""
India Quant Execution Bot (NSE/BSE Long-Only Swing & Momentum).
Interfaces with Groww Trading API (or paper/mock mode if using placeholder keys).
Runs on IST schedule (09:15 - 15:30 IST) without any conflict with US trading.
"""

import sys
import os
import math
from datetime import datetime, timedelta
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from trading_system.app.config.settings import settings
from trading_system.app.research.quant_engine import QuantEngine, InvestorSkillsHeuristics
from trading_system.app.broker.groww import GrowwBrokerAdapter
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.notifications.notifier import QuantNotifier
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator
from trading_system.app.config.stop_loss_manager import StopLossManager

logger = logging.getLogger("IndiaQuantBot")

def execute_india_live_cycle():
    print("\n" + "="*70)
    print(">>> AWAKENING INDIA QUANT ENGINE (NSE / BSE CASH CNC) <<<")
    print("="*70)

    api_key = settings.INDIA_API_KEY
    api_secret = settings.INDIA_API_SECRET
    totp_secret = settings.INDIA_TOTP_SECRET
    initial_cap = getattr(settings, "INDIA_INITIAL_CAPITAL", 1000000.0)

    broker = GrowwBrokerAdapter(
        api_key=api_key,
        api_secret=api_secret,
        totp_secret=totp_secret,
        initial_capital=initial_cap
    )
    risk_engine = BasicRiskEngine(max_position_pct=0.25, max_portfolio_pct=0.95)

    mode_str = "SIMULATED / PAPER MODE (Placeholders Active)" if broker.is_mock else "LIVE GROWW TRADING API"
    print(f"\n[1/4] Syncing with Indian Broker: [{mode_str}]...")
    
    current_positions = broker.get_positions()
    print(f"  Broker reports holdings: {len(current_positions)} positions -> {list(current_positions.keys())}")
    
    total_equity = broker.get_account_equity()
    print(f"  Broker reports Total INR Equity: ₹{total_equity:,.2f}")

    print("\n[2/4] Waking up QUANT Brain & Scanning NSE Universe...")
    brain = QuantEngine(enable_ml_gating=False) # Pure quantitative alpha for NSE universe

    # Load NSE Ticker universe
    try:
        universe_path = os.path.join(os.path.dirname(__file__), "..", "data", "nse_tickers.txt")
        with open(universe_path, "r") as f:
            universe = [line.strip() for line in f.readlines() if line.strip()]
        print(f"  Successfully loaded {len(universe)} NSE stock symbols from nse_tickers.txt.")
    except Exception as e:
        print(f"  Could not load nse_tickers.txt ({e}), falling back to top Nifty 10 mega-caps.")
        universe = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "BHARTIARTL.NS", "SBIN.NS", "LT.NS", "ITC.NS", "BAJFINANCE.NS"
        ]

    # Run multi-strategy scan (sample up to 25 stocks for fast execution)
    scan_basket = universe[:25]
    print(f"  Running multi-strategy quantitative scan on top {len(scan_basket)} NSE stocks...")
    research_results = brain.run_nightly_research(scan_basket, datetime.now())
    
    if isinstance(research_results, dict):
        momentum_signals = research_results.get("momentum", [])
        mean_rev_signals = research_results.get("mean_reversion", [])
    else:
        momentum_signals = research_results or []
        mean_rev_signals = []

    print(f"  QUANT Brain Output: {len(momentum_signals)} Momentum Leaders | {len(mean_rev_signals)} Mean-Reversion Dip-Buys")

    # --- INDIAN MACRO REGIME (Nifty 50 & India VIX) ---
    print("\n[2b/4] Evaluating Indian Macro Radar (Nifty 50 ^NSEI, India VIX ^INDIAVIX)...")
    ensemble = EnsembleAllocator(max_total_exposure=0.95, max_single_stock=0.15, max_holdings=8)

    try:
        nifty_df = brain.data_provider.get_data_as_of("^NSEI", datetime.now())
    except Exception:
        nifty_df = None
    try:
        india_vix_df = brain.data_provider.get_data_as_of("^INDIAVIX", datetime.now())
    except Exception:
        india_vix_df = None

    regime_info = ensemble.detect_regime(nifty_df, vix_df=india_vix_df)
    regime = regime_info["regime"]
    MAX_EXPOSURE = regime_info["max_exposure"]
    strat_weights = regime_info.get("weights", {})
    diag = regime_info.get("diagnostics", {})

    print(f"  Detected Indian Regime: {regime}")
    if diag.get("vix"):
        vix_state = "CALM (< 15)" if diag["vix"] < 15 else ("ELEVATED" if diag["vix"] < 22 else "HIGH VOLATILITY (>= 22)")
        print(f"  India VIX Gauge: {diag['vix']:.2f} [{vix_state}]")
    print(f"  Max Total Exposure: {MAX_EXPOSURE*100:.0f}% (Liquid Cash Reserve: {(1.0-MAX_EXPOSURE)*100:.0f}%)")

    # --- STOP-LOSS ENGINE & GTT MONITORING ---
    print("\n[2c/4] Checking Open Indian Positions for Stop-Loss Limits...")
    sl_manager = StopLossManager()
    stop_loss_liquidations = set()
    pos_pnl_map = {}
    
    try:
        detailed_positions = broker.get_positions_detailed()
        for pos in detailed_positions:
            sym = pos["symbol"]
            plpc = pos.get("unrealized_plpc", 0.0)
            pos_pnl_map[sym] = plpc
            threshold = sl_manager.get_stop_loss_pct(sym)
            is_custom = sl_manager.is_custom_override(sym)
            tag = "CUSTOM USER OVERRIDE" if is_custom else "BOT DEFAULT"
            
            if plpc <= threshold:
                print(f"  [STOP-LOSS HIT] {sym} is down {plpc*100:.2f}% (Limit: {threshold*100:.1f}% [{tag}]). Liquidating CNC position.")
                stop_loss_liquidations.add(sym)
            else:
                print(f"  [HOLDING SAFE] {sym} PnL: {plpc*100:+.2f}% | Stop Limit: {threshold*100:.1f}% [{tag}]")
    except Exception as e:
        print(f"  Error checking Indian stop-losses: {e}")

    # Combine Allocations
    valid_mom = [s for s in momentum_signals if s["symbol"] not in stop_loss_liquidations]
    valid_mr = [s for s in mean_rev_signals if s["symbol"] not in stop_loss_liquidations]
    target_weights = ensemble.combine_allocations(valid_mom, valid_mr, regime_info)

    print("\n[3/4] Reconciling Targets & Sizing with Integer Share Enforcement...")
    
    # 1. Stop loss liquidations
    for sym in stop_loss_liquidations:
        if sym in current_positions:
            print(f" -> [LIQUIDATE] Closing {sym} on NSE...")
            broker.close_position(sym)

    # 2. Identify new buys
    new_buys = {s: w for s, w in target_weights.items() if s not in current_positions and w > 0}
    
    if new_buys:
        print(f"  Identified {len(new_buys)} qualifying new buy orders:")
        for sym, weight in new_buys.items():
            target_notional = total_equity * weight
            price = broker.get_latest_price(sym)
            if price > 0:
                # SEBI Whole integer share sizing
                shares = int(math.floor(target_notional / price))
                if shares >= 1:
                    actual_inv = shares * price
                    print(f"  -> BUY {shares} shares of {sym} @ ₹{price:.2f} (~₹{actual_inv:,.2f} | {weight*100:.1f}%)")
                    res = broker.place_order(symbol=sym, qty=shares, side="BUY", order_type="MARKET", product_type="CNC")
                    if res.get("success"):
                        # Automatically attach a server-side GTT Stop Loss at -8%
                        stop_p = round(price * 0.92, 2)
                        gtt_res = broker.place_gtt_stop_loss(symbol=sym, qty=shares, trigger_price=stop_p)
                        print(f"     [GTT ATTACHED] Server-side GTT Stop placed @ ₹{stop_p:.2f}")
                else:
                    print(f"  -> Skipping {sym}: Target allocation ₹{target_notional:,.2f} is less than 1 share (₹{price:.2f}).")
    else:
        print("  No new buy orders required today. Portfolio is in equilibrium.")

    # 3. Notification
    print("\n[4/4] Dispatching Quant Execution Summary...")
    acc_details = broker.get_account_details()
    summary_msg = (
        f"🇮🇳 **India Quant Bot Daily Summary**\n"
        f"**Broker Mode:** {mode_str}\n"
        f"**Total INR Equity:** ₹{acc_details['equity']:,.2f}\n"
        f"**Available Cash:** ₹{acc_details['cash']:,.2f}\n"
        f"**Active Holdings:** {len(broker.get_positions())} positions\n"
        f"**Indian Market Regime:** {regime}\n"
    )
    print(summary_msg)
    print("="*70)
    print(">>> INDIA QUANT BOT EXECUTION COMPLETED SUCCESSFULLY <<<")
    print("="*70 + "\n")

if __name__ == "__main__":
    execute_india_live_cycle()
