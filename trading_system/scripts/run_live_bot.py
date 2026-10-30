"""
Production Live/Paper Trading Bot Engine
Architecture: High-Alpha Concentration Edition (Top 10 Leaders, Trailing Runners, Macro Radar)
"""
import os
import sys
import time
import math
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np
import joblib

from trading_system.app.config.settings import settings
from trading_system.app.config.stop_loss_manager import StopLossManager
from trading_system.app.data.yfinance_provider import YFinanceDataProvider
from trading_system.app.features.regime import InstitutionalMacroRegimeEngine
from trading_system.app.strategies.ensembles.ensemble_allocator import EnsembleAllocator
from trading_system.app.ml.feature_pipeline import MLFeaturePipeline
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine

MODEL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "models", "quant_rf_model.joblib")
STOP_LOSS_CONFIG = os.path.join(PROJECT_ROOT, "trading_system", "app", "config", "stop_loss_config.json")

# Core S&P 500 liquid candidate universe for daily scanning
CORE_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "LLY",
    "UNH", "V", "MA", "COST", "HD", "PG", "NFLX", "AMD", "CRM", "ADBE",
    "QCOM", "TXN", "INTU", "AMAT", "NOW", "CAT", "GE", "ISRG", "UBER", "PANW",
    "BKNG", "AXP", "GS", "MS", "SPGI", "BLK", "MCD", "DIS", "WMT", "XOM"
]

MACRO_SYMBOLS = {
    "spy": "SPY",
    "vix": "^VIX",
    "qqq": "QQQ",
    "hyg": "HYG",
    "ief": "IEF",
    "tnx": "^TNX",
    "irx": "^IRX",
    "rsp": "RSP"
}

def execute_live_cycle(dry_run: bool = False):
    print("\n" + "="*80)
    print(">>> AWAKENING HIGH-ALPHA PRODUCTION BOT ENGINE <<<")
    print("Architecture: Top 10 Concentrated Leadership (10% Target) + Trailing Runners")
    print("Safety Shield: Institutional 4-Pillar Macro Radar + ML Alpha Gating")
    print("="*80)
    
    API_KEY = settings.PAPER_API_KEY
    API_SECRET = settings.PAPER_API_SECRET
    
    if not API_KEY or not API_SECRET:
        print("WARNING: PAPER_API_KEY / PAPER_API_SECRET not detected in .env.")
        print("Running in DRY-RUN simulation mode (no live broker orders).")
        dry_run = True
        
    data_provider = YFinanceDataProvider()
    stop_manager = StopLossManager(STOP_LOSS_CONFIG)
    macro_engine = InstitutionalMacroRegimeEngine()
    allocator = EnsembleAllocator(max_total_exposure=0.98, max_single_stock=0.12, max_holdings=10, min_position_pct=0.04)
    ml_pipeline = MLFeaturePipeline()
    ml_model = joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None
    
    broker = AlpacaBrokerAdapter(api_key=API_KEY, api_secret=API_SECRET) if not dry_run else None
    execution = AlpacaExecutionAdapter(api_key=API_KEY, api_secret=API_SECRET) if not dry_run else None
    risk_engine = BasicRiskEngine(max_position_size=500000)
    
    # 1. Sync Live State
    print("\n[1/6] Syncing with Broker for LIVE Account State...")
    detailed_positions = []
    positions_map = {}
    if not dry_run:
        try:
            current_positions = broker.get_positions()
            detailed_positions = broker.get_positions_detailed()
            positions_map = {p["symbol"]: p for p in detailed_positions}
            total_equity = broker.get_account_equity()
        except Exception as e:
            print(f"Error fetching live account state: {e}. Switching to simulation baseline.")
            current_positions = {}
            detailed_positions = []
            positions_map = {}
            total_equity = 10000.0
            dry_run = True
    else:
        current_positions = {}
        total_equity = 10000.0
        
    print(f"  Account Equity : ${total_equity:,.2f}")
    print(f"  Open Positions : {len(current_positions)} held {list(current_positions.keys())}")
    
    # 2. Ingest Macro Data & Evaluate Institutional Macro Weather
    print("\n[2/6] Ingesting Live Macro Instruments (T-200 Days)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    macro_dfs = {}
    for key, sym in MACRO_SYMBOLS.items():
        try:
            df = data_provider.fetch_historical_data(sym, start_date, end_date)
            if not df.empty:
                macro_dfs[key] = df
        except Exception as e:
            print(f"  Warning: failed to fetch {sym}: {e}")
            
    regime_info = macro_engine.evaluate(
        spy_df=macro_dfs.get("spy"),
        vix_df=macro_dfs.get("vix"),
        qqq_df=macro_dfs.get("qqq"),
        hyg_df=macro_dfs.get("hyg"),
        ief_df=macro_dfs.get("ief"),
        tnx_df=macro_dfs.get("tnx"),
        irx_df=macro_dfs.get("irx"),
        rsp_df=macro_dfs.get("rsp")
    )
    regime = regime_info["regime"]
    max_exposure = regime_info.get("max_exposure", 0.98)
    msi = regime_info.get("macro_stress_index", 0.0)
    print(f"  Macro Radar Status : REGIME = [{regime}] | Stress Index = {msi:.2f} | Max Gross Exposure = {max_exposure*100:.1f}%")
    
    # 3. Evaluate Open Positions & Dynamic Runner Exits
    print("\n[3/6] Evaluating Active Positions for Multi-Tier Exits...")
    positions_to_liquidate = []
    
    if regime == "CRASH_WARNING":
        print("  >>> [CRASH WARNING ALERT] 100% CASH DEFENSE ACTIVATED. LIQUIDATING ALL ASSETS. <<<")
        for sym in current_positions.keys():
            positions_to_liquidate.append((sym, "CRASH_WARNING_100PCT_CASH"))
    else:
        for sym, qty in current_positions.items():
            if qty <= 0:
                continue
            df_sym = data_provider.fetch_historical_data(sym, end_date - timedelta(days=90), end_date)
            if df_sym.empty or len(df_sym) < 20:
                continue
            current_price = df_sym["close"].iloc[-1]
            sma50 = df_sym["close"].rolling(50, min_periods=20).mean().iloc[-1]
            
            # Fetch actual entry price and peak price for dynamic runner stops
            pos_info = positions_map.get(sym, {})
            avg_entry = float(pos_info.get("avg_entry_price", current_price))
            peak_price = max(float(df_sym["high"].tail(60).max()), current_price, avg_entry)
            
            exit_decision = stop_manager.evaluate_dynamic_exit(
                symbol=sym,
                current_price=current_price,
                avg_entry=avg_entry,
                peak_price=peak_price,
                sma50=sma50,
                holding_type="MOMENTUM"
            )
            if exit_decision["should_exit"]:
                positions_to_liquidate.append((sym, exit_decision["reason"]))
                
    # 4. Ingest Candidate Universe & Generate Causal Technical Signals
    sp500_file = os.path.join(PROJECT_ROOT, "trading_system", "data", "sp500_tickers.txt")
    scan_universe = CORE_UNIVERSE
    if os.path.exists(sp500_file):
        try:
            with open(sp500_file, "r") as f:
                loaded = [line.strip().replace('.', '-') for line in f if line.strip()]
            if len(loaded) >= 40:
                scan_universe = loaded[:100]
        except Exception:
            scan_universe = CORE_UNIVERSE

    print(f"\n[4/6] Scanning {len(scan_universe)} S&P 500 Leaders for Breakouts & Dips...")
    universe_data = {}
    mom_candidates = []
    mr_candidates = []
    
    for sym in scan_universe:
        try:
            df = data_provider.fetch_historical_data(sym, end_date - timedelta(days=300), end_date)
            if len(df) < 50:
                continue
            universe_data[sym] = df
            
            close = df["close"]
            sma20 = close.rolling(20, min_periods=20).mean().iloc[-1]
            sma50 = close.rolling(50, min_periods=50).mean().iloc[-1]
            price = close.iloc[-1]
            
            # Momentum Breakout: Price > 20 SMA > 50 SMA
            if price > sma20 and sma20 > sma50:
                roc20 = (price - close.iloc[-21]) / close.iloc[-21] if len(close) > 21 else 0.0
                vol20 = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)
                if roc20 > 0.03:
                    score = roc20 / (vol20 + 0.05) if (vol20 + 0.05) > 0 else roc20
                    mom_candidates.append({
                        "symbol": sym,
                        "price": price,
                        "score": score,
                        "conviction_score": score,
                        "signal": 1,
                        "type": "MOMENTUM",
                        "df": df
                    })
                    
            # Mean Reversion Dip: Price near lower Bollinger Band & RSI < 35
            bb_std = close.rolling(20).std().iloc[-1]
            bb_lower = sma20 - (2.0 * bb_std)
            delta = close.diff()
            gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean().iloc[-1]
            loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean().iloc[-1]
            rsi = 100.0 - (100.0 / (1.0 + (gain / loss))) if loss > 0 else 50.0
            
            if price <= (bb_lower * 1.01) and rsi < 35.0:
                mr_candidates.append({
                    "symbol": sym,
                    "price": price,
                    "score": (35.0 - rsi),
                    "confidence": 0.85,
                    "signal": 1,
                    "type": "DIP_BUY",
                    "df": df
                })
        except Exception:
            pass
            
    print(f"  Detected {len(mom_candidates)} Momentum Leaders and {len(mr_candidates)} Oversold Dip Opportunities.")
    
    # 5. ML Alpha Gating
    print("\n[5/6] Gating Candidates with Random Forest ML Alpha Classifier...")
    qualified_candidates = []
    candidates_to_eval = sorted(mom_candidates, key=lambda x: x["score"], reverse=True)[:10] + sorted(mr_candidates, key=lambda x: x["score"], reverse=True)[:5]
    
    feat_cols = list(ml_model.feature_names_in_) if ml_model is not None else []
    for cand in candidates_to_eval:
        sym = cand["symbol"]
        df_c = cand["df"]
        prob = 0.50
        if ml_model is not None:
            try:
                feats = ml_pipeline.extract_features(df_c)
                last_row = feats[feat_cols].iloc[-1:].values
                if not np.isnan(last_row).any():
                    prob = float(ml_model.predict_proba(last_row)[:, 1][0])
            except Exception:
                prob = 0.50
        cand["ml_prob"] = prob
        if prob >= 0.38:
            qualified_candidates.append(cand)
            print(f"  [PASSED GATE] {sym:<6} | Type: {cand['type']:<8} | Score: {cand['score']:5.2f} | ML Prob: {prob*100:.1f}%")
            
    # 6. Ensemble Allocation (Top 10 Concentrated Positions)
    print("\n[6/6] High-Alpha Portfolio Construction (Top 10 Leaders, 10% each)...")
    target_weights = allocator.combine_allocations(
        momentum_signals=[c for c in qualified_candidates if c["type"] == "MOMENTUM"],
        mean_rev_signals=[c for c in qualified_candidates if c["type"] == "DIP_BUY"],
        regime_info=regime_info
    )
    print(f"  Target Portfolio Allocations: {target_weights}")
    
    # Reconcile Orders
    reconciled_orders = []
    # A. Sells from liquidations
    for sym, reason in positions_to_liquidate:
        qty = current_positions.get(sym, 0.0)
        if qty > 0:
            reconciled_orders.append({"symbol": sym, "side": "SELL", "quantity": qty, "reason": reason})
            
    # B. Buys for target allocations
    for sym, weight in target_weights.items():
        if sym in current_positions:
            continue  # Already held, let runner ride
        dollar_target = total_equity * weight
        price = universe_data[sym]["close"].iloc[-1] if sym in universe_data else 100.0
        shares = round(dollar_target / price, 4)
        if shares > 0 and dollar_target >= 50.0:
            reconciled_orders.append({"symbol": sym, "side": "BUY", "quantity": shares, "reason": f"ENTRY_TARGET_{weight*100:.1f}%"})
            
    print(f"\n  Reconciled Orders to Execute: {len(reconciled_orders)}")
    for order in reconciled_orders:
        sym = order["symbol"]
        side = order["side"]
        qty = order["quantity"]
        reason = order["reason"]
        print(f"    --> ROUTING ORDER: {side:<4} {qty:8.2f} shares of {sym:<6} | Reason: {reason}")
        
        if not dry_run and execution is not None:
            order_hash = f"HIGH_ALPHA_{datetime.now().date()}_{sym}_{side}_{qty}"
            client_id = f"HA-{hashlib.md5(order_hash.encode()).hexdigest()[:12]}"
            trade_req = {
                "client_order_id": client_id,
                "symbol": sym,
                "side": side.lower(),
                "quantity": int(qty),
                "price_hint": universe_data.get(sym, {}).get("close", pd.Series([100.0])).iloc[-1]
            }
            if risk_engine.evaluate_trade(trade_req, current_positions):
                execution.submit_order(trade_req)
            else:
                print(f"    [RISK REJECT] Order failed risk check: {sym}")
                
    print("\n" + "="*80)
    print("SUCCESS: HIGH-ALPHA LIVE EXECUTION CYCLE COMPLETE.")
    print("="*80 + "\n")

if __name__ == "__main__":
    execute_live_cycle()
