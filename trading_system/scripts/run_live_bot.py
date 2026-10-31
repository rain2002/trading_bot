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
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter, BrokerAPIError
from trading_system.app.broker.groww import GrowwBrokerAdapter
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
from trading_system.app.risk.basic import BasicRiskEngine
from trading_system.app.portfolio.position_tracker import PositionTracker
from trading_system.app.config.market_config import MarketConfig

MODEL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "models", "quant_rf_model.joblib")
STOP_LOSS_CONFIG = os.path.join(PROJECT_ROOT, "trading_system", "app", "config", "stop_loss_config.json")

# Default core fallback universe
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
    print("Safety Shield: Universal Macro Radar + Rules-Based Dynamic Allocation")
    print("="*80)

    market_code = os.environ.get("TRADING_MARKET", "US")
    market = MarketConfig.load(market_code)
    print(f"Target Market: [{market.country} - {market.name}] | Benchmark: {market.benchmark_symbol} ({market.currency_symbol})")
    print(f"Broker Adapter: {market.broker_adapter.upper()} | Integer Shares Only: {market.integer_shares_only}")

    data_provider = YFinanceDataProvider()
    stop_manager = StopLossManager(STOP_LOSS_CONFIG)
    macro_engine = InstitutionalMacroRegimeEngine()
    allocator = EnsembleAllocator(
        max_total_exposure=0.98,
        max_single_stock=market.max_single_stock,
        max_holdings=market.max_holdings,
        min_position_pct=market.min_position_pct
    )
    ml_pipeline = MLFeaturePipeline()
    ml_model = joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None

    broker = None
    execution = None
    if not dry_run:
        if market.broker_adapter == "groww":
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
            execution = broker
        else:
            API_KEY = settings.PAPER_API_KEY
            API_SECRET = settings.PAPER_API_SECRET
            if not API_KEY or not API_SECRET:
                print("WARNING: PAPER_API_KEY / PAPER_API_SECRET not detected in .env.")
                print("Running in DRY-RUN simulation mode (no live broker orders).")
                dry_run = True
            else:
                broker = AlpacaBrokerAdapter(api_key=API_KEY, api_secret=API_SECRET)
                execution = AlpacaExecutionAdapter(api_key=API_KEY, api_secret=API_SECRET)

    risk_engine = BasicRiskEngine(max_position_pct=market.max_single_stock, max_portfolio_pct=0.95)
    pos_tracker = PositionTracker()
    
    # 1. Sync Live State
    print("\n[1/6] Syncing with Broker for LIVE Account State...")
    detailed_positions = []
    positions_map = {}
    if not dry_run and broker is not None:
        try:
            current_positions = broker.get_positions()
            detailed_positions = broker.get_positions_detailed()
            positions_map = {p["symbol"]: p for p in detailed_positions}
            total_equity = broker.get_account_equity()
            recent_orders = broker.get_recent_orders(limit=200)
            pos_tracker.sync_with_broker(current_positions, detailed_positions, recent_orders)
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
        
    print(f"  Account Equity : {market.currency_symbol}{total_equity:,.2f}")
    print(f"  Open Positions : {len(current_positions)} held {list(current_positions.keys())}")
    
    # 2. Ingest Macro Data & Evaluate Institutional Macro Weather
    print(f"\n[2/6] Ingesting Live Macro Instruments for {market.market_code} (T-200 Days)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    if market.market_code == "US":
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
    else:
        # Non-US: Universal Local-Index evaluation on local benchmark and local vix
        local_benchmark_df = data_provider.fetch_historical_data(market.benchmark_symbol, start_date, end_date)
        local_vix_sym = "^INDIAVIX" if market.market_code == "IN" else None
        local_vix_df = data_provider.fetch_historical_data(local_vix_sym, start_date, end_date) if local_vix_sym else None
        regime_info = macro_engine.evaluate(index_df=local_benchmark_df, vix_df=local_vix_df)
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
            
            # Fetch actual entry price, holding type, and peak price strictly since entry
            pos_info = positions_map.get(sym, {})
            pos_meta = pos_tracker.get_position_meta(sym)
            h_type = pos_meta.get("holding_type", "MOMENTUM")
            entry_dt = pos_meta.get("entry_date")
            avg_entry = float(pos_meta.get("entry_price") or pos_info.get("avg_entry_price", current_price))
            
            # Peak strictly on or after entry date (avoids pre-entry historical highs)
            if entry_dt and hasattr(df_sym.index, 'date'):
                try:
                    df_since = df_sym[df_sym.index >= pd.to_datetime(entry_dt)]
                    peak_price = float(df_since["high"].max()) if not df_since.empty else current_price
                except Exception:
                    peak_price = current_price
            else:
                peak_price = current_price
            peak_price = max(peak_price, current_price, avg_entry)
            
            # Mean reversion indicators if dip buy
            sma20_s = df_sym["close"].rolling(20, min_periods=10).mean()
            bb_mid = float(sma20_s.iloc[-1]) if not sma20_s.empty else current_price
            delta = df_sym["close"].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=min(14, len(df_sym)), adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=min(14, len(df_sym)), adjust=False).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            rsi_val = float((100.0 - (100.0 / (1.0 + rs))).iloc[-1]) if not rs.empty else 50.0

            exit_decision = stop_manager.evaluate_dynamic_exit(
                symbol=sym,
                current_price=current_price,
                avg_entry=avg_entry,
                peak_price=peak_price,
                sma50=sma50,
                holding_type=h_type,
                bb_mid=bb_mid,
                rsi=rsi_val
            )
            if exit_decision["should_exit"]:
                positions_to_liquidate.append((sym, exit_decision["reason"]))
                pos_tracker.record_exit(sym)
                
    # 4. Ingest Candidate Universe & Generate Causal Technical Signals
    scan_universe = market.get_universe()
    if not scan_universe:
        scan_universe = CORE_UNIVERSE

    print(f"\n[4/6] Scanning {len(scan_universe)} Leaders in {market.name} for Breakouts & Dips...")
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
    
    # 5. Candidate Ranking & Optional ML Alpha Gating (Rules-Only Default)
    enable_ml_gating = os.environ.get("ENABLE_ML_GATING", "false").lower() == "true"
    qualified_candidates = []
    candidates_to_eval = sorted(mom_candidates, key=lambda x: x["score"], reverse=True)[:10] + sorted(mr_candidates, key=lambda x: x["score"], reverse=True)[:5]
    
    if not enable_ml_gating or ml_model is None:
        print("\n[5/6] Ranking Candidates via Pure Rules-Based Conviction (Rules-Only Mode Active)...")
        for cand in candidates_to_eval:
            cand["ml_prob"] = 0.50
            qualified_candidates.append(cand)
            print(f"  [QUALIFIED LEADER] {cand['symbol']:<6} | Type: {cand['type']:<8} | Conviction Score: {cand['score']:5.2f}")
    else:
        print("\n[5/6] Gating Candidates with Random Forest ML Alpha Classifier...")
        feat_cols = list(ml_model.feature_names_in_) if ml_model is not None else []
        for cand in candidates_to_eval:
            sym = cand["symbol"]
            df_c = cand["df"]
            prob = 0.50
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
            if market.integer_shares_only or not market.supports_fractional:
                qty = float(math.floor(qty))
            p_curr = universe_data.get(sym, {}).get("close", pd.Series([100.0])).iloc[-1]
            est_friction = market.calculate_transaction_costs(qty * p_curr, qty, "SELL")
            reconciled_orders.append({
                "symbol": sym,
                "side": "SELL",
                "quantity": qty,
                "reason": reason,
                "estimated_friction": est_friction
            })
            
    # B. Buys for target allocations (strictly capped by max_exposure)
    held_val = 0.0
    for s, q in current_positions.items():
        p_c = universe_data[s]["close"].iloc[-1] if (s in universe_data and not universe_data[s].empty) else 100.0
        held_val += q * p_c
    held_exposure = held_val / total_equity if total_equity > 0 else 0.0
    available_capacity = max(0.0, max_exposure - held_exposure)
    
    new_buys = {s: w for s, w in target_weights.items() if s not in current_positions and w > 0.0}
    sum_buys = sum(new_buys.values())
    if sum_buys > available_capacity and sum_buys > 0:
        scale = available_capacity / sum_buys
        new_buys = {s: round(w * scale, 4) for s, w in new_buys.items()}
    
    for sym, weight in new_buys.items():
        if available_capacity <= 0.02:
            break
        dollar_target = total_equity * weight
        price = universe_data[sym]["close"].iloc[-1] if (sym in universe_data and not universe_data[sym].empty) else 100.0
        raw_shares = dollar_target / price
        if market.integer_shares_only or not market.supports_fractional:
            shares = float(math.floor(raw_shares))
        else:
            shares = round(raw_shares, 4)

        min_val = 50.0 if market.currency_code == "USD" else 1000.0
        if shares > 0 and dollar_target >= min_val:
            is_dip = any(c["symbol"] == sym for c in mr_candidates)
            tag = "DIP_BUY" if is_dip else "MOMENTUM"
            est_friction = market.calculate_transaction_costs(dollar_target, shares, "BUY")
            reconciled_orders.append({
                "symbol": sym,
                "side": "BUY",
                "quantity": shares,
                "reason": f"ENTRY_{tag}_{weight*100:.1f}%",
                "estimated_friction": est_friction
            })
            
    # Sort: SELLS first, then BUYS
    reconciled_orders.sort(key=lambda o: 0 if o["side"] == "SELL" else 1)
    print(f"\n  Reconciled Orders to Execute: {len(reconciled_orders)}")
    
    current_invested_value = held_val
    for order in reconciled_orders:
        sym = order["symbol"]
        side = order["side"]
        qty = order["quantity"]
        reason = order["reason"]
        friction = order.get("estimated_friction", 0.0)
        print(f"    --> ROUTING ORDER: {side:<4} {qty:8.2f} shares of {sym:<6} | Reason: {reason} | Est Friction: {market.currency_symbol}{friction:.2f}")
        
        if not dry_run and execution is not None:
            order_hash = f"HIGH_ALPHA_{datetime.now().date()}_{sym}_{side}_{qty}"
            client_id = f"HA-{hashlib.md5(order_hash.encode()).hexdigest()[:12]}"
            trade_price = universe_data.get(sym, {}).get("close", pd.Series([100.0])).iloc[-1]
            trade_req = {
                "client_order_id": client_id,
                "symbol": sym,
                "side": side.lower(),
                "quantity": round(qty, 4),
                "price_hint": trade_price
            }
            if risk_engine.evaluate_trade(trade_req, current_positions, total_equity=total_equity, current_invested_value=current_invested_value):
                res = execution.submit_order(trade_req)
                if res.get("status") in ("SUBMITTED", "FILLED"):
                    if side == "SELL":
                        current_invested_value = max(0.0, current_invested_value - (qty * trade_price))
                        current_positions[sym] = max(0.0, current_positions.get(sym, 0.0) - qty)
                        if current_positions[sym] <= 1e-4:
                            pos_tracker.record_exit(sym)
                    else:
                        current_invested_value += qty * trade_price
                        current_positions[sym] = current_positions.get(sym, 0.0) + qty
                        h_type = "DIP_BUY" if "DIP" in reason else "MOMENTUM"
                        pos_tracker.record_entry(sym, h_type, trade_price, quantity=qty)
                else:
                    print(f"    [ORDER FAILED] Broker rejected {sym}: {res.get('error', res.get('status'))}")
            else:
                print(f"    [RISK REJECT] Order failed risk check: {sym}")
                
    print("\n" + "="*80)
    print("SUCCESS: HIGH-ALPHA LIVE EXECUTION CYCLE COMPLETE.")
    print("="*80 + "\n")

if __name__ == "__main__":
    execute_live_cycle()
