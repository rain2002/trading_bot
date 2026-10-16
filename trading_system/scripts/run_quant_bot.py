import sys
import os
from datetime import datetime, timedelta
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from trading_system.app.config.settings import settings
from trading_system.app.research.quant_engine import QuantEngine, InvestorSkillsHeuristics
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.notifications.notifier import QuantNotifier
from trading_system.app.features.regime import RegimeDetector

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
    
    # Run the multi-agent research pipeline for today
    generated_signals = brain.run_nightly_research(universe, datetime.now())
    print(f"QUANT Brain generated {len(generated_signals)} signals based on InvestorSkills heuristics.")
    
    # --- REGIME DETECTION (Market Weather Check) ---
    print("\n[2b/4] Detecting Market Regime via SPY...")
    regime = "BULL_NORMAL"
    try:
        spy_df = brain.data_provider.get_data_as_of("SPY", datetime.now())
        if not spy_df.empty and len(spy_df) >= 200:
            regime = RegimeDetector().detect_regime(spy_df)
    except Exception as e:
        print(f"  Regime detection failed, defaulting to BULL_NORMAL: {e}")

    # Map regime to maximum portfolio exposure
    REGIME_EXPOSURE = {
        "BULL_NORMAL":   0.95,  # Full throttle
        "BULL_VOLATILE": 0.70,  # Reduce risk, high vol
        "BEAR_NORMAL":   0.30,  # Defensive — only highest conviction
        "BEAR_VOLATILE": 0.20,  # Highly defensive
        "CRASH_WARNING": 0.00,  # Move to 100% cash
        "UNKNOWN":       0.50,  # Cautious default
    }
    MAX_EXPOSURE = REGIME_EXPOSURE.get(regime, 0.50)
    print(f"  Regime: {regime} → Max Portfolio Exposure: {MAX_EXPOSURE*100:.0f}%")

    if regime == "CRASH_WARNING":
        print("  ⚠️  CRASH WARNING: Moving to 100% cash. No new buys.")

    # --- STOP-LOSS ENGINE (-8% Max Loss per Position) ---
    print("\n[2c/4] Checking Open Positions for Hard Stop-Loss (-8%)...")
    stop_loss_liquidations = set()
    try:
        detailed_positions = broker.get_positions_detailed()
        for pos in detailed_positions:
            sym = pos["symbol"]
            plpc = pos.get("unrealized_plpc", 0.0)
            if plpc <= -0.08:
                print(f"  🛑 [STOP-LOSS] {sym} is down {plpc*100:.2f}% (Limit: -8.0%). Forcing full liquidation.")
                stop_loss_liquidations.add(sym)
    except Exception as e:
        print(f"  Stop-loss check encountered error: {e}")

    # --- DYNAMIC SIZING ENGINE WITH TOP-25 CONVICTION FILTER ---
    # Max single stock exposure: 15%
    # Max portfolio holdings: 25 top conviction leaders (concentrates alpha)
    MAX_HOLDINGS = 25
    target_weights = {}

    # Filter candidates: must have strictly positive conviction score and not be stopped out
    valid_signals = [
        s for s in (generated_signals or [])
        if s.get("conviction_score", 0.0) > 0.0 and s["symbol"] not in stop_loss_liquidations
    ]

    if valid_signals and MAX_EXPOSURE > 0:
        # Sort candidates descending by conviction score (Risk-Adjusted Momentum)
        sorted_signals = sorted(
            valid_signals,
            key=lambda s: s.get("conviction_score", 0.0),
            reverse=True
        )
        selected_signals = sorted_signals[:MAX_HOLDINGS]
        total_selected = len(selected_signals)
        
        print(f"\nDynamic Sizing Engine: Filtered {len(generated_signals)} candidates down to Top {total_selected} Positive Conviction Leaders (Max {MAX_HOLDINGS})...")
        
        # Conviction-proportional sizing (alpha-weighted capital distribution)
        total_score = sum(s.get("conviction_score", 1.0) for s in selected_signals)
        
        for sig in selected_signals:
            sym = sig["symbol"]
            score = sig.get("conviction_score", 1.0)
            # Allocate proportional to conviction score, bounded by single-stock cap (15%)
            prop_weight = (score / total_score) * MAX_EXPOSURE if total_score > 0 else (MAX_EXPOSURE / total_selected)
            assigned_weight = min(prop_weight, 0.15)
            target_weights[sym] = round(assigned_weight, 4)
            print(f" -> {sym:<6}: {assigned_weight*100:4.1f}% | Score: {score:>5.2f} ({sig['rationale']})")
    else:
        if MAX_EXPOSURE == 0.0:
            print(f"Market Regime is {regime}. Preserving 100% Cash.")
        else:
            print("No positive conviction signals generated today. Moving to 100% Cash.")
    # ----------------------------
        
    print("\n[3/4] Reconciling QUANT Targets against Broker State...")
    
    # Ensure any open positions no longer wanted or stopped out are liquidated
    for open_sym in current_positions.keys():
        if open_sym not in target_weights or open_sym in stop_loss_liquidations:
            target_weights[open_sym] = 0.0
            
    print("\n[4/4] Routing Orders to Risk Engine & Alpaca...")
    executed_orders_log = []
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
                
        target_value = total_equity * target_weight
        
        current_qty = current_positions.get(sym, 0.0)
        current_value = current_qty * current_price
        
        value_to_trade = target_value - current_value
        qty_to_trade = int(value_to_trade / current_price)
        
        if qty_to_trade != 0:
            side = "BUY" if qty_to_trade > 0 else "SELL"
            import hashlib
            run_date = datetime.now().date()
            order_hash_base = f"QUANT_{run_date}_{sym}_{side}_{qty_to_trade}"
            deterministic_id = f"QUANT-{hashlib.md5(order_hash_base.encode()).hexdigest()[:12]}"
            
            trade_request = {
                "client_order_id": deterministic_id,
                "symbol": sym,
                "quantity": qty_to_trade,
                "price_hint": current_price
            }
            if risk_engine.evaluate_trade(trade_request, current_positions, total_equity=total_equity):
                execution.submit_order(trade_request)
                executed_orders_log.append({"symbol": sym, "side": side, "qty": qty_to_trade})
                print(f" -> EXECUTED: {side} {abs(qty_to_trade)} {sym}")
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
