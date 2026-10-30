"""
26-Year High-Alpha Trial Run (2000-2025)
Focus: Concentrated Leadership, Trend-Following Runners, Zero Lookahead Bias
Starting Capital: $1,000 USD (No External Additions)
"""
import os
import sys
import time
import math
import warnings
import pandas as pd
import numpy as np
import joblib

warnings.filterwarnings("ignore")

# Setup paths
PROJECT_ROOT = r"D:\paper_trading_bot"
sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.ml.feature_pipeline import MLFeaturePipeline

CACHE_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data", "historical_cache")
REGIME_CACHE_FILE = os.path.join(CACHE_DIR, "macro_regimes_2000_2025.parquet")
MODEL_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "models", "quant_rf_model.joblib")

INITIAL_CAPITAL = 1000.0
SLIPPAGE_BPS = 5.0
MAX_POSITIONS = 12  # Concentrated portfolio (vs 144 before)
TARGET_POS_WEIGHT = 0.085  # ~8.5% per position

def normalize_index(df):
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index.date)
    return df

def run_high_alpha_backtest():
    print("="*80)
    print(">>> RUNNING 26-YEAR HIGH-ALPHA TRIAL RUN (2000 - 2025) <<<")
    print(f"Starting Capital: ${INITIAL_CAPITAL:,.2f} USD")
    print(f"Portfolio Architecture: Concentrated Leadership (Max {MAX_POSITIONS} positions)")
    print("Exit Philosophy: Let Winners Run (50-SMA Trend Following + ATR Trailing)")
    print("="*80)
    
    t0 = time.time()
    
    # 1. Load Data
    reg_df = pd.read_parquet(REGIME_CACHE_FILE)
    spy_df = pd.read_parquet(os.path.join(CACHE_DIR, "SPY.parquet"))
    spy_df = normalize_index(spy_df)
    spy_df.columns = [c.lower() for c in spy_df.columns]
    
    ml_model = joblib.load(MODEL_PATH)
    ml_pipeline = MLFeaturePipeline()
    feat_cols = list(ml_model.feature_names_in_)
    
    # Load stock parquets
    stock_universe = {}
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith(".parquet") and not fname.startswith("INDEX_") and fname not in ["SPY.parquet", "QQQ.parquet", "HYG.parquet", "IEF.parquet", "RSP.parquet", "macro_regimes_2000_2025.parquet"]:
            sym = fname.replace(".parquet", "")
            try:
                sdf = pd.read_parquet(os.path.join(CACHE_DIR, fname))
                if len(sdf) >= 100:
                    sdf = normalize_index(sdf)
                    sdf.columns = [c.lower() for c in sdf.columns]
                    stock_universe[sym] = sdf
            except Exception:
                pass
                
    print(f"Loaded {len(stock_universe)} stocks in {time.time()-t0:.2f}s")
    
    # 2. Precompute Causal Rolling Features
    t1 = time.time()
    precalc = {}
    for sym, df in stock_universe.items():
        close = df["close"]
        high = df.get("high", close)
        low = df.get("low", close)
        divs = df.get("dividends", pd.Series(0.0, index=df.index))
        
        sma20 = close.rolling(20, min_periods=20).mean()
        sma50 = close.rolling(50, min_periods=50).mean()
        sma200 = close.rolling(200, min_periods=50).mean()
        roc20 = (close - close.shift(20)) / close.shift(20)
        vol20 = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
        
        bb_std = close.rolling(20, min_periods=20).std()
        bb_lower = sma20 - (2.0 * bb_std)
        bb_mid = sma20
        
        # Wilder's RSI
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        p_feats = None
        try:
            feats = ml_pipeline.extract_features(df)
            p_feats = feats[feat_cols].values
        except Exception:
            pass
            
        precalc[sym] = {
            "dates": df.index,
            "close": close.values,
            "high": high.values,
            "low": low.values,
            "dividends": divs.values,
            "sma20": sma20.values,
            "sma50": sma50.values,
            "sma200": sma200.values,
            "roc20": roc20.values,
            "vol20": vol20.values,
            "bb_lower": bb_lower.values,
            "bb_mid": bb_mid.values,
            "rsi": rsi.values,
            "ml_values": p_feats,
            "date_to_idx": {d: i for i, d in enumerate(df.index)}
        }
    print(f"Precomputed features in {time.time()-t1:.2f}s")
    
    # 3. Execution Loop
    timeline = sorted(list(reg_df.index))
    cash = INITIAL_CAPITAL
    positions = {}       # sym -> shares
    entry_prices = {}    # sym -> entry fill
    peak_prices = {}     # sym -> highest price reached since entry (for trailing profit lock)
    holding_types = {}   # sym -> "MOMENTUM" or "DIP_BUY"
    
    trade_log = []
    equity_curve = {}
    total_divs = 0.0
    
    t_sim = time.time()
    for day_idx, current_date in enumerate(timeline):
        reg_row = reg_df.loc[current_date]
        regime = reg_row["regime"]
        
        # In Bull regimes, maximize capital utilization (96% exposure)
        if regime in ["BULL_TRENDING", "BULL_ROTATION"]:
            max_exposure = 0.96
        elif regime == "VOLATILITY_CAUTION":
            max_exposure = 0.70
        elif regime in ["BEAR_CORRECTION", "CREDIT_DIVERGENCE_CAUTION"]:
            max_exposure = 0.40
        else: # CRASH_WARNING
            max_exposure = 0.0
            
        # A. Mark to market & process dividends
        current_prices = {}
        for sym, shares in list(positions.items()):
            p_sym = precalc[sym]
            if current_date in p_sym["date_to_idx"]:
                idx = p_sym["date_to_idx"][current_date]
                price = p_sym["close"][idx]
                high = p_sym["high"][idx]
                current_prices[sym] = price
                
                # Update peak price for trailing runner
                if price > peak_prices.get(sym, price):
                    peak_prices[sym] = price
                    
                # Dividends
                div_ps = p_sym["dividends"][idx]
                if div_ps > 0.0:
                    div_amt = shares * div_ps
                    cash += div_amt
                    total_divs += div_amt
                    
        total_equity = cash + sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        
        # B. Exits & Liquidations
        liquidations = []
        if regime == "CRASH_WARNING":
            # 100% Cash Defense
            for sym in list(positions.keys()):
                liquidations.append((sym, "CRASH_WARNING_DEFENSE"))
        else:
            for sym, shares in list(positions.items()):
                if sym not in current_prices or sym not in precalc:
                    continue
                price = current_prices[sym]
                cost = entry_prices.get(sym, price)
                peak = peak_prices.get(sym, price)
                plpc = (price - cost) / cost if cost > 0 else 0.0
                p_sym = precalc[sym]
                idx = p_sym["date_to_idx"][current_date]
                h_type = holding_types.get(sym, "MOMENTUM")
                
                # 1. Hard stop loss (-8%)
                if plpc <= -0.08:
                    liquidations.append((sym, f"HARD_STOP (-8%) [Loss: {plpc*100:.1f}%]"))
                    continue
                    
                # 2. Dip-Buy profit target
                if h_type == "DIP_BUY":
                    bb_mid = p_sym["bb_mid"][idx]
                    rsi_val = p_sym["rsi"][idx]
                    if (not math.isnan(bb_mid) and price >= bb_mid) or (not math.isnan(rsi_val) and rsi_val >= 58.0):
                        liquidations.append((sym, f"DIP_TARGET_EXIT [PnL: {plpc*100:+.1f}%]"))
                        continue
                        
                # 3. Momentum Runner Exits (Let Winners Run!)
                if h_type == "MOMENTUM":
                    sma50 = p_sym["sma50"][idx]
                    
                    # Trend breakdown: Closed below 50-day SMA by > 2%
                    if not math.isnan(sma50) and price < (sma50 * 0.98):
                        liquidations.append((sym, f"TREND_50SMA_BREAK [PnL: {plpc*100:+.1f}%]"))
                        continue
                        
                    # Trailing Runner Lock: If position reached +25% profit, don't let it give back more than 12% from peak
                    gain_from_cost = (peak - cost) / cost if cost > 0 else 0.0
                    if gain_from_cost >= 0.25:
                        drawdown_from_peak = (peak - price) / peak if peak > 0 else 0.0
                        if drawdown_from_peak >= 0.12:
                            liquidations.append((sym, f"RUNNER_PROFIT_LOCK [Locked: {plpc*100:+.1f}% | Peak was {gain_from_cost*100:+.1f}%]"))
                            continue
                            
        # Execute sells
        for sym, reason in liquidations:
            shares = positions[sym]
            price = current_prices.get(sym, entry_prices.get(sym, 0.0))
            fill_price = price * (1.0 - SLIPPAGE_BPS / 10000.0)
            proceeds = shares * fill_price
            cash += proceeds
            cost = entry_prices.get(sym, price)
            gain = proceeds - (shares * cost)
            
            trade_log.append({
                "date": current_date,
                "symbol": sym,
                "action": "SELL",
                "shares": shares,
                "price": fill_price,
                "realized_pnl": gain,
                "pnl_pct": (fill_price - cost) / cost if cost > 0 else 0.0,
                "reason": reason
            })
            del positions[sym]
            entry_prices.pop(sym, None)
            peak_prices.pop(sym, None)
            holding_types.pop(sym, None)
            
        total_equity = cash + sum(positions[s] * current_prices.get(s, 0.0) for s in positions)
        
        # C. Signal Generation & Concentrated Position Entries
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0 and max_exposure > 0.0 and regime != "CRASH_WARNING":
            held_exposure = sum(positions[s] * current_prices.get(s, 0.0) for s in positions) / total_equity if total_equity > 0 else 0.0
            available_capacity = max(0.0, max_exposure - held_exposure)
            
            if available_capacity > 0.04 and cash > 25.0:
                # Scan candidates
                mom_cands = []
                mr_cands = []
                for sym, p_sym in precalc.items():
                    if sym in positions or current_date not in p_sym["date_to_idx"]:
                        continue
                    idx = p_sym["date_to_idx"][current_date]
                    if idx < 50:
                        continue
                    price = p_sym["close"][idx]
                    sma20 = p_sym["sma20"][idx]
                    sma50 = p_sym["sma50"][idx]
                    sma200 = p_sym["sma200"][idx]
                    
                    if math.isnan(price) or math.isnan(sma20) or math.isnan(sma50):
                        continue
                        
                    # Momentum: Strong trend above 20 & 50 SMA, 20-day ROC
                    if price > sma20 and sma20 > sma50 and (math.isnan(sma200) or price > sma200):
                        roc = p_sym["roc20"][idx]
                        vol = p_sym["vol20"][idx]
                        if not math.isnan(roc) and not math.isnan(vol) and roc > 0.02:
                            score = roc / (vol + 0.05)
                            mom_cands.append({"symbol": sym, "idx": idx, "price": price, "score": score})
                            
                    # Mean Reversion: Oversold dip
                    bb_low = p_sym["bb_lower"][idx]
                    rsi_v = p_sym["rsi"][idx]
                    if not math.isnan(bb_low) and not math.isnan(rsi_v) and price <= (bb_low * 1.01) and rsi_v < 36.0:
                        mr_cands.append({"symbol": sym, "idx": idx, "price": price, "rsi": rsi_v})
                        
                # ML Alpha evaluation on top candidates
                top_mom = sorted(mom_cands, key=lambda x: x["score"], reverse=True)[:10]
                eval_rows = []
                eval_cands = []
                for cand in top_mom:
                    sym = cand["symbol"]
                    idx = cand["idx"]
                    ml_v = precalc[sym]["ml_values"]
                    if ml_v is not None and idx < len(ml_v) and not np.isnan(ml_v[idx]).any():
                        eval_rows.append(ml_v[idx])
                        eval_cands.append(cand)
                    else:
                        cand["ml_prob"] = 0.50
                        
                if eval_rows:
                    probs = ml_model.predict_proba(np.array(eval_rows))[:, 1]
                    for cand, prob in zip(eval_cands, probs):
                        cand["ml_prob"] = prob
                        
                # Filter high conviction
                valid_entries = [c for c in top_mom if c.get("ml_prob", 0.0) >= 0.40]
                
                # Sizing: Target ~8.5% of equity per position
                target_dollar_per_pos = total_equity * TARGET_POS_WEIGHT
                
                for cand in valid_entries[:open_slots]:
                    if cash < 25.0:
                        break
                    sym = cand["symbol"]
                    price = cand["price"]
                    fill_price = price * (1.0 + SLIPPAGE_BPS / 10000.0)
                    alloc = min(target_dollar_per_pos, cash * 0.95)
                    
                    if alloc >= 20.0:
                        shares = round(alloc / fill_price, 4)
                        cost = shares * fill_price
                        if cost <= cash and shares > 0:
                            cash -= cost
                            positions[sym] = shares
                            entry_prices[sym] = fill_price
                            peak_prices[sym] = price
                            current_prices[sym] = price
                            holding_types[sym] = "MOMENTUM"
                            
                            trade_log.append({
                                "date": current_date,
                                "symbol": sym,
                                "action": "BUY",
                                "shares": shares,
                                "price": fill_price,
                                "realized_pnl": 0.0,
                                "pnl_pct": 0.0,
                                "reason": f"ENTRY_MOM [Score: {cand['score']:.2f} | ML: {cand.get('ml_prob', 0.5):.2f}]"
                            })
                            
        daily_equity = cash + sum(positions[s] * current_prices.get(s, entry_prices.get(s, 0.0)) for s in positions)
        equity_curve[current_date] = round(daily_equity, 2)
        
        if (day_idx + 1) % 1000 == 0 or (day_idx + 1) == len(timeline):
            print(f"  [{current_date.date()}] Day {day_idx+1:4d}/{len(timeline)} | Equity: ${daily_equity:10,.2f} | Cash: ${cash:8,.2f} | Holdings: {len(positions):2d} | Regime: {regime}")
            
    print(f"\nExecution finished in {time.time()-t_sim:.2f}s!")
    
    # Analyze
    eq_series = pd.Series(equity_curve)
    final_eq = eq_series.iloc[-1]
    years = len(timeline) / 252.0
    cagr = ((final_eq / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    tot_ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    
    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = dd.min() * 100.0
    
    ret_daily = eq_series.pct_change().dropna()
    sharpe = (ret_daily.mean() / ret_daily.std()) * np.sqrt(252)
    sortino = (ret_daily.mean() / ret_daily[ret_daily < 0].std()) * np.sqrt(252)
    
    closed = [t for t in trade_log if t["action"] == "SELL"]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100.0 if closed else 0.0
    
    gross_p = sum(t["realized_pnl"] for t in wins)
    gross_l = abs(sum(t["realized_pnl"] for t in closed if t["realized_pnl"] <= 0))
    pf = gross_p / gross_l if gross_l > 0 else 0.0
    
    print("\n" + "="*80)
    print("="*20 + " HIGH-ALPHA RUN RESULTS " + "="*20)
    print("="*80)
    print(f"Starting Capital         : ${INITIAL_CAPITAL:,.2f}")
    print(f"Final Account Equity     : ${final_eq:,.2f}")
    print(f"Total Cumulative Return  : {tot_ret:+,.2f}%")
    print(f"Compound Annual Growth   : {cagr:.2f}%")
    print(f"Max Drawdown             : {max_dd:.2f}%")
    print(f"Sharpe Ratio             : {sharpe:.2f}")
    print(f"Sortino Ratio            : {sortino:.2f}")
    print(f"Total Dividends Paid In  : ${total_divs:,.2f}")
    print(f"Total Trades Executed    : {len(trade_log)} ({len(closed)} closed)")
    print(f"Win Rate                 : {win_rate:.2f}%")
    print(f"Profit Factor            : {pf:.2f}")
    print("="*80)
    
    # Save equity curve
    out_path = os.path.join(CACHE_DIR, "equity_curve_high_alpha.csv")
    eq_series.to_csv(out_path)
    print(f"Saved high-alpha equity curve to {out_path}")

if __name__ == "__main__":
    run_high_alpha_backtest()
