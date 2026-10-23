import sys
import os
import hashlib
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
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.notifications.notifier import QuantNotifier
from trading_system.app.features.regime import RegimeDetector
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator

logger = logging.getLogger("QUANTBot")

def execute_quant_live_cycle():
    print("\n" + "="*50)
    print(">>> AWAKENING QUANT BRAIN (TRADING AGENTS MVP) <<<")
    print("="*50)
    
    API_KEY = settings.PAPER_API_KEY
    API_SECRET = settings.PAPER_API_SECRET
    
    if not API_KEY or not API_SECRET:
        print("ERROR: PAPER_API_KEY or PAPER_API_SECRET not found.")
        return
        
    broker = AlpacaBrokerAdapter(api_key=API_KEY, api_secret=API_SECRET)
    execution = AlpacaExecutionAdapter(api_key=API_KEY, api_secret=API_SECRET)
    risk_engine = BasicRiskEngine(max_position_pct=0.15, max_portfolio_pct=0.95)
    
    print("\n[1/4] Syncing with Broker for LIVE Positions...")
    current_positions = broker.get_positions()
    print(f"Broker reports we hold: {current_positions}")
    total_equity = broker.get_account_equity()
    print(f"Broker reports Total Account Equity: ${total_equity:,.2f}")
    
    print("\n[2/4] Waking up QUANT Trading Agents & Fetching OpenBB Data...")
    brain = QuantEngine()
    
    # Dynamically fetch the entire S&P 500 universe
    print("Fetching the complete S&P 500 universe for maximum opportunity scanning...")
    try:
        import os
        filepath = os.path.join(os.path.dirname(__file__), "..", "data", "sp500_tickers.txt")
        with open(filepath, "r") as f:
            universe = [line.strip().replace('.', '-') for line in f.readlines() if line.strip()]
        print(f"Successfully loaded {len(universe)} S&P 500 symbols from local dataset.")
    except Exception as e:
        print(f"Failed to load S&P 500 file, falling back to mega-caps. Error: {e}")
        universe = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"]
    
    # Run the multi-strategy research pipeline for today
    research_results = brain.run_nightly_research(universe, datetime.now())
    if isinstance(research_results, dict):
        momentum_signals = research_results.get("momentum", [])
        mean_rev_signals = research_results.get("mean_reversion", [])
    else:
        momentum_signals = research_results or []
        mean_rev_signals = []

    print(f"QUANT Brain generated: {len(momentum_signals)} Momentum Leaders | {len(mean_rev_signals)} Mean-Reversion Dip-Buys")
    
    # --- PHASE 2: ENSEMBLE REGIME DETECTION & ALLOCATION ---
    print("\n[2b/4] Evaluating Macro Weather via Ensemble Allocator (SPY)...")
    ensemble = EnsembleAllocator(max_total_exposure=0.95, max_single_stock=0.15, max_holdings=25)
    
    spy_df = brain.data_provider.get_data_as_of("SPY", datetime.now())
    regime_info = ensemble.detect_regime(spy_df)
    regime = regime_info["regime"]
    MAX_EXPOSURE = regime_info["max_exposure"]
    strat_weights = regime_info.get("weights", {})
    
    print(f"  Detected Regime: {regime}")
    print(f"  Max Total Exposure: {MAX_EXPOSURE*100:.0f}% (Liquid Cash Reserve: {(1.0-MAX_EXPOSURE)*100:.0f}%)")
    print(f"  Strategy Mix: Momentum={strat_weights.get('momentum', 0)*100:.0f}% | Dip-Buying={strat_weights.get('mean_reversion', 0)*100:.0f}%")

    if regime == "CRASH_WARNING":
        print("  [CRASH WARNING] Moving to 100% Cash Buffer. Preserving capital.")

    # --- STOP-LOSS ENGINE (-8% Max Loss per Position) ---
    print("\n[2c/4] Checking Open Positions for Hard Stop-Loss (-8%)...")
    stop_loss_liquidations = set()
    try:
        detailed_positions = broker.get_positions_detailed()
        for pos in detailed_positions:
            sym = pos["symbol"]
            plpc = pos.get("unrealized_plpc", 0.0)
            if plpc <= -0.08:
                print(f"  [STOP-LOSS] {sym} is down {plpc*100:.2f}% (Limit: -8.0%). Forcing full liquidation.")
                stop_loss_liquidations.add(sym)
    except Exception as e:
        print(f"  Stop-loss check encountered error: {e}")

    # --- COMBINE ALLOCATIONS VIA ENSEMBLE ALLOCATOR ---
    # Filter candidates: exclude any stopped out symbols
    valid_mom = [s for s in momentum_signals if s["symbol"] not in stop_loss_liquidations]
    valid_mr = [s for s in mean_rev_signals if s["symbol"] not in stop_loss_liquidations]
    
    target_weights = ensemble.combine_allocations(valid_mom, valid_mr, regime_info)

    if target_weights:
        print(f"\nPhase 2 Ensemble: Allocated to Top {len(target_weights)} Holdings (Max 25):")
        for sym, weight in sorted(target_weights.items(), key=lambda x: x[1], reverse=True):
            # Check strategy attribution
            is_mom = any(s["symbol"] == sym for s in valid_mom)
            is_mr = any(s["symbol"] == sym for s in valid_mr)
            tag = "MOM+DIP" if (is_mom and is_mr) else ("MOMENTUM" if is_mom else "DIP-BUY")
            print(f" -> {sym:<6}: {weight*100:4.1f}% | Strategy: [{tag}]")
    else:
        if MAX_EXPOSURE == 0.0:
            print(f"Market Regime is {regime}. Holding 100% Cash.")
        else:
            print("No qualifying signals today. Holding 100% Cash.")
    # ----------------------------
        
    print("\n[3/4] Reconciling QUANT Targets against Broker State...")
    
    # Cancel any pending/stale orders on broker to prevent wash-trade blocks and duplicate fills
    print(" -> Canceling any pending orders on broker for clean state...")
    broker.cancel_all_orders()
    
    # Re-sync positions in case fills happened
    current_positions = broker.get_positions()
    
    # Ensure any open positions no longer wanted or stopped out are marked for full liquidation
    for open_sym in current_positions.keys():
        if open_sym not in target_weights or open_sym in stop_loss_liquidations:
            target_weights[open_sym] = 0.0
            
    print("\n[4/4] Routing Orders to Risk Engine & Alpaca...")
    executed_orders_log = []
    run_timestamp_tag = datetime.now().strftime('%Y%m%d_%H%M')
    
    planned_trades = []
    for sym, target_weight in target_weights.items():
        if target_weight == 'HOLD':
            continue
            
        current_price = broker.get_latest_price(sym)
        if current_price <= 0:
            df = brain.data_provider.get_data_as_of(sym, datetime.now())
            if not df.empty and 'close' in df:
                current_price = float(df['close'].iloc[-1])
                
        # Protect against phantom price executions: skip order if price cannot be verified
        if current_price <= 0:
            print(f" -> [PRICE REJECT] Could not determine market price for {sym}. Skipping order to protect capital.")
            continue
                
        current_qty = current_positions.get(sym, 0.0)
        
        # If target is 0.0, liquidate exactly all held shares without truncation residue
        if target_weight == 0.0:
            qty_to_trade = -int(round(current_qty))
        else:
            target_value = total_equity * target_weight
            current_value = current_qty * current_price
            value_to_trade = target_value - current_value
            qty_to_trade = int(round(value_to_trade / current_price))
        
        # Ensure we never sell more shares than currently held (no inadvertent short positions)
        if qty_to_trade < 0 and abs(qty_to_trade) > current_qty:
            qty_to_trade = -int(round(current_qty))
        
        if qty_to_trade != 0:
            side = "BUY" if qty_to_trade > 0 else "SELL"
            planned_trades.append({
                "symbol": sym,
                "quantity": qty_to_trade,
                "side": side,
                "price_hint": current_price
            })
            
    # INSTITUTIONAL ROUTING: Prioritize SELLS before BUYS
    # Liquidating/trimming first frees capital, eliminates margin deficits, and reduces exposure
    planned_trades.sort(key=lambda t: 0 if t["side"] == "SELL" else 1)
    
    # Track current invested dollar value in real time
    try:
        detailed_positions = broker.get_positions_detailed()
        if detailed_positions:
            current_invested_value = sum(float(p.get("market_value", 0.0)) for p in detailed_positions)
        else:
            current_invested_value = sum(abs(qty) * broker.get_latest_price(s) for s, qty in current_positions.items())
    except Exception:
        current_invested_value = sum(abs(qty) * broker.get_latest_price(s) for s, qty in current_positions.items())

    for trade in planned_trades:
        sym = trade["symbol"]
        qty_to_trade = trade["quantity"]
        side = trade["side"]
        current_price = trade["price_hint"]
        
        order_hash_base = f"QUANT_{run_timestamp_tag}_{sym}_{side}_{abs(qty_to_trade)}"
        deterministic_id = f"Q-{hashlib.md5(order_hash_base.encode()).hexdigest()[:14]}"
        
        trade_request = {
            "client_order_id": deterministic_id,
            "symbol": sym,
            "quantity": qty_to_trade,
            "side": side,
            "price_hint": current_price
        }
        if risk_engine.evaluate_trade(trade_request, current_positions, total_equity=total_equity, current_invested_value=current_invested_value):
            result = execution.submit_order(trade_request)
            if result.get("status") in ("SUBMITTED", "FILLED"):
                executed_orders_log.append({"symbol": sym, "side": side, "qty": abs(qty_to_trade)})
                print(f" -> EXECUTED: {side} {abs(qty_to_trade)} {sym}")
                # Dynamically update position state & invested value for subsequent orders
                if side == "SELL":
                    current_invested_value = max(0.0, current_invested_value - (abs(qty_to_trade) * current_price))
                    current_positions[sym] = max(0.0, current_positions.get(sym, 0.0) - abs(qty_to_trade))
                else:
                    current_invested_value += abs(qty_to_trade) * current_price
                    current_positions[sym] = current_positions.get(sym, 0.0) + abs(qty_to_trade)
            else:
                print(f" -> [BROKER REJECT] Order failed for {sym}: {result.get('error', result.get('status'))}")
        else:
            print(f" -> [RISK HALT] Trade rejected by Risk Engine: {sym} {qty_to_trade}")

    print("\n[5/5] Dispatching Daily Quant Summary Notification...")
    notifier = QuantNotifier()
    try:
        acc_details = broker.get_account_details()
        open_pos_count = len(broker.get_positions())
        regime_description = f"{regime} (Max Exposure: {int(MAX_EXPOSURE*100)}%)"
        notifier.send_daily_summary(
            equity=acc_details["equity"],
            cash=acc_details["cash"],
            open_positions_count=open_pos_count,
            executed_orders=executed_orders_log,
            today_pnl=acc_details["today_pnl"],
            today_pnl_pct=acc_details["today_pnl_pct"],
            overall_pnl=acc_details["overall_pnl"],
            overall_pnl_pct=acc_details["overall_pnl_pct"],
            regime_info=regime_description
        )
    except Exception as e:
        print(f"Notification dispatch failed: {e}")
                
    print("\nSUCCESS: QUANT BRAIN EXECUTION CYCLE COMPLETE.")
    print("="*50 + "\n")

if __name__ == "__main__":
    execute_quant_live_cycle()
