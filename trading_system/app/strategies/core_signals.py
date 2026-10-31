"""
Core Quant Strategy: Authoritative Signal Generation and Multi-Tier Position Exits.

Unified module shared identically across Backtesting, Paper Trading, and Live Execution.
Prevents logic drift between research and production.

Strategy Rules:
1. Momentum Breakout (Trend Following):
   - Price > 20-SMA > 50-SMA
   - 20-day Rate of Change > 3%
   - Score: ROC20 / (RealizedVol20 + 0.05)
   - Exits: Hard Stop (-8%), Breakeven Ratchet (+12% peak -> lock +2%),
     Big Winner Trailing Stop (+30% peak -> trail 14% below peak),
     Trend Breakdown (Price < 97.5% of 50-SMA).
   - NOTE: Momentum positions are NEVER subjected to mean-reversion profit exits!

2. Mean-Reversion Dip Buy (High-Quality Pullback):
   - Price <= Lower Bollinger Band * 1.01 AND RSI(14) < 35.0
   - Bonus score if Price > 200-SMA (pullback within secular uptrend)
   - Score: (35.0 - RSI) * (1.2 if Price > 200-SMA else 1.0)
   - Exits: Hard Stop (-8%), or Reversion Target Reached:
     (Price >= Middle Bollinger Band and PnL >= +4%) OR RSI >= 60.0 OR PnL >= +12%.

3. Portfolio Sizing:
   - Target 10 equal slots (10.0% target weight each, 12.0% hard cap).
   - When fewer than 10 candidates qualify, DO NOT inflate single-stock caps to 25%.
   - Keep each qualified holding at ~10% and preserve the rest in CASH buffer.
"""

import math
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd


# Canonical institutional parameters (frozen)
DEFAULT_FAST_SMA = 20
DEFAULT_SLOW_SMA = 50
DEFAULT_TARGET_WEIGHT = 0.10
DEFAULT_MAX_SINGLE_STOCK = 0.12
DEFAULT_MAX_HOLDINGS = 10
DEFAULT_HARD_STOP_PCT = -0.08
DEFAULT_BREAKEVEN_TRIGGER_PCT = 0.12
DEFAULT_BREAKEVEN_LOCK_PCT = 0.02
DEFAULT_RUNNER_TRIGGER_PCT = 0.30
DEFAULT_RUNNER_TRAIL_DD_PCT = 0.14
DEFAULT_50SMA_BUFFER_PCT = 0.025


def calculate_technical_features(df: pd.DataFrame, fast_sma: int = DEFAULT_FAST_SMA, slow_sma: int = DEFAULT_SLOW_SMA) -> pd.DataFrame:
    """Computes technical indicators for momentum and mean-reversion signals."""
    out = df.copy()
    close = out.get("adj_close", out["close"])
    
    # Moving averages
    out["sma_fast"] = close.rolling(window=fast_sma, min_periods=max(5, fast_sma // 2)).mean()
    out["sma_slow"] = close.rolling(window=slow_sma, min_periods=max(10, slow_sma // 2)).mean()
    out["sma_200"] = close.rolling(window=200, min_periods=30).mean()
    
    # 20-day ROC and Realized Volatility
    out["roc_20"] = close.pct_change(20)
    out["ret_1d"] = close.pct_change()
    out["vol_20"] = out["ret_1d"].rolling(20, min_periods=10).std() * np.sqrt(252)
    
    # Bollinger Bands (20-day, 2 std)
    sma_20 = close.rolling(20, min_periods=10).mean()
    std_20 = close.rolling(20, min_periods=10).std()
    out["bb_mid"] = sma_20
    out["bb_lower"] = sma_20 - 2.0 * std_20
    out["bb_upper"] = sma_20 + 2.0 * std_20
    
    # RSI (14-day Wilder)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    out["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
    
    return out


def generate_candidate_signals(
    universe_data: Dict[str, pd.DataFrame],
    regime: str = "BULL_TRENDING",
    max_holdings: int = DEFAULT_MAX_HOLDINGS,
    fast_sma: int = DEFAULT_FAST_SMA,
    slow_sma: int = DEFAULT_SLOW_SMA,
    ml_gate_func: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Scans universe for Momentum Breakouts and Oversold Dip Buys.
    Returns ranked candidate list and target portfolio weights.
    """
    if regime == "CRASH_WARNING":
        return {
            "candidates": [],
            "target_weights": {},
            "regime": regime,
            "rationale": "CRASH_WARNING active: 100% Cash Defense."
        }

    mom_candidates = []
    dip_candidates = []

    for sym, df in universe_data.items():
        if df is None or df.empty or len(df) < max(slow_sma, 35):
            continue

        close_s = df.get("adj_close", df["close"])
        curr_price = float(close_s.iloc[-1])
        if curr_price <= 0 or math.isnan(curr_price):
            continue

        # SMAs
        sma_fast_val = float(close_s.rolling(fast_sma, min_periods=10).mean().iloc[-1])
        sma_slow_val = float(close_s.rolling(slow_sma, min_periods=20).mean().iloc[-1])
        sma_200_s = close_s.rolling(200, min_periods=30).mean()
        sma_200_val = float(sma_200_s.iloc[-1]) if not sma_200_s.empty and not math.isnan(sma_200_s.iloc[-1]) else curr_price

        # 1. Momentum Signal
        if curr_price > sma_fast_val and sma_fast_val > sma_slow_val:
            roc_20 = float(close_s.pct_change(20).iloc[-1]) if len(close_s) > 20 else 0.0
            ret_1d = close_s.pct_change().tail(20)
            vol_20 = float(ret_1d.std() * np.sqrt(252)) if len(ret_1d) >= 10 else 0.25

            if not math.isnan(roc_20) and not math.isnan(vol_20) and roc_20 > 0.03:
                score = roc_20 / (vol_20 + 0.05)
                mom_candidates.append({
                    "symbol": sym,
                    "price": curr_price,
                    "score": float(score),
                    "holding_type": "MOMENTUM",
                    "sma_fast": sma_fast_val,
                    "sma_slow": sma_slow_val,
                    "roc_20": roc_20,
                    "vol_20": vol_20
                })

        # 2. Mean-Reversion Dip Buy Signal
        sma_20 = close_s.rolling(20, min_periods=10).mean()
        std_20 = close_s.rolling(20, min_periods=10).std()
        bb_low = float((sma_20 - 2.0 * std_20).iloc[-1]) if not std_20.empty else curr_price
        bb_mid = float(sma_20.iloc[-1]) if not sma_20.empty else curr_price

        # RSI 14
        delta = close_s.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi_14 = float((100.0 - (100.0 / (1.0 + rs))).iloc[-1]) if not rs.empty else 50.0

        if not math.isnan(bb_low) and not math.isnan(rsi_14) and curr_price <= (bb_low * 1.01) and rsi_14 < 35.0:
            quality_boost = 1.2 if curr_price > sma_200_val else 1.0
            score = (35.0 - rsi_14) * quality_boost
            dip_candidates.append({
                "symbol": sym,
                "price": curr_price,
                "score": float(score),
                "holding_type": "DIP_BUY",
                "bb_low": bb_low,
                "bb_mid": bb_mid,
                "rsi_14": rsi_14,
                "sma_200": sma_200_val
            })

    # Sort each pool
    mom_candidates.sort(key=lambda x: x["score"], reverse=True)
    dip_candidates.sort(key=lambda x: x["score"], reverse=True)

    # Balance by regime
    if regime in ("BULL_TRENDING", "BULL_ROTATION"):
        # Prioritize momentum
        selected_pool = mom_candidates[:8] + dip_candidates[:4]
    else:
        # Prioritize oversold dips in corrections / caution
        selected_pool = dip_candidates[:8] + mom_candidates[:4]

    # Optional ML alpha gate
    if ml_gate_func is not None and callable(ml_gate_func):
        vetted_pool = []
        for cand in selected_pool:
            try:
                passed, prob = ml_gate_func(cand["symbol"], universe_data[cand["symbol"]])
                cand["ml_prob"] = prob
                if passed:
                    vetted_pool.append(cand)
            except Exception:
                cand["ml_prob"] = 0.50
                vetted_pool.append(cand)
        selected_pool = vetted_pool

    # Re-sort combined by score and take up to max_holdings
    selected_pool.sort(key=lambda x: x["score"], reverse=True)
    final_candidates = selected_pool[:max_holdings]

    # Equal 10% target weights (capped at 12%), strictly NO ballooning to 25%
    target_weights: Dict[str, float] = {}
    for cand in final_candidates:
        target_weights[cand["symbol"]] = DEFAULT_TARGET_WEIGHT

    return {
        "candidates": final_candidates,
        "target_weights": target_weights,
        "regime": regime,
        "momentum_count": len(mom_candidates),
        "dip_count": len(dip_candidates)
    }


def evaluate_holding_exit(
    symbol: str,
    current_price: float,
    avg_entry: float,
    peak_price: Optional[float] = None,
    holding_type: str = "MOMENTUM",
    sma50: Optional[float] = None,
    bb_mid: Optional[float] = None,
    rsi: Optional[float] = None,
    regime: str = "BULL_TRENDING",
    hard_stop_pct: float = DEFAULT_HARD_STOP_PCT,
    breakeven_trigger_pct: float = DEFAULT_BREAKEVEN_TRIGGER_PCT,
    breakeven_lock_pct: float = DEFAULT_BREAKEVEN_LOCK_PCT,
    runner_trigger_pct: float = DEFAULT_RUNNER_TRIGGER_PCT,
    runner_dd_pct: float = DEFAULT_RUNNER_TRAIL_DD_PCT,
    trend_50sma_buffer_pct: float = DEFAULT_50SMA_BUFFER_PCT,
) -> Dict[str, Any]:
    """
    Authoritative exit evaluation for open positions.
    CRITICAL: Disentangles MOMENTUM from DIP_BUY positions.
    - MOMENTUM positions NEVER exit on mean-reversion/RSI profit targets.
    - DIP_BUY positions exit on BB mid / RSI reversion or profit target.
    - Peak price MUST be strictly measured from bars on or after entry date.
    """
    if avg_entry <= 0 or current_price <= 0:
        return {"should_exit": False, "action": "HOLD", "reason": "Invalid entry or price"}

    # 1. Macro Regime Crash Guardrail
    if regime == "CRASH_WARNING":
        return {
            "should_exit": True,
            "action": "CRASH_WARNING_DEFENSE",
            "reason": "Market in CRASH_WARNING. Liquidating holding to 100% Cash Defense."
        }

    # Calculate PnL from entry
    plpc = (current_price - avg_entry) / avg_entry

    # 2. Hard Stop-Loss (-8% default or user override)
    effective_stop = -abs(hard_stop_pct)
    if plpc <= effective_stop:
        return {
            "should_exit": True,
            "action": "HARD_STOP",
            "reason": f"HARD_STOP ({effective_stop*100:.1f}%) breached [PnL: {plpc*100:+.2f}%]"
        }

    # Peak price since entry (must never be lower than entry or current)
    peak = max(peak_price if peak_price is not None and not math.isnan(peak_price) else current_price, current_price, avg_entry)
    gain_from_cost = (peak - avg_entry) / avg_entry

    # -------------------------------------------------------------------------
    # ROUTE A: DIP-BUY POSITIONS (Mean-Reversion Swing Trades)
    # -------------------------------------------------------------------------
    if str(holding_type).upper() in ("DIP_BUY", "DIP-BUY", "MEAN_REVERSION"):
        # Reversion target: Price reaches 20-SMA (BB Mid) with positive gain, or RSI normalizes >= 60, or +12% profit
        hit_bb_mid = (bb_mid is not None and not math.isnan(bb_mid) and current_price >= bb_mid and plpc >= 0.04)
        hit_rsi = (rsi is not None and not math.isnan(rsi) and rsi >= 60.0)
        hit_target = (plpc >= 0.12)

        if hit_bb_mid or hit_rsi or hit_target:
            trigger_reason = "20-SMA BB Mid Reached" if hit_bb_mid else ("RSI >= 60 Rebound" if hit_rsi else "+12% Profit Target")
            return {
                "should_exit": True,
                "action": "DIP_TARGET_EXIT",
                "reason": f"DIP_TARGET_EXIT: {trigger_reason} [PnL: {plpc*100:+.2f}%]"
            }

        # Otherwise: Dip buy is still consolidating or rebounding, hold unless hard stop breached
        return {
            "should_exit": False,
            "action": "HOLD",
            "reason": f"Dip-Buy active [PnL: {plpc*100:+.2f}%]. Holding for mean rebound."
        }

    # -------------------------------------------------------------------------
    # ROUTE B: MOMENTUM POSITIONS (Trend-Following Multi-Bagger Runners)
    # -------------------------------------------------------------------------
    # 1. Breakeven Ratchet: If position peaked at >= +12%, lock in minimum +2% profit
    if gain_from_cost >= breakeven_trigger_pct and plpc <= breakeven_lock_pct:
        return {
            "should_exit": True,
            "action": "BREAKEVEN_STOP",
            "reason": f"BREAKEVEN_STOP triggered: Peaked at +{gain_from_cost*100:.1f}%, securing +{plpc*100:+.2f}% gain."
        }

    # 2. Big Winner Trailing Stop: If reached >= +30% profit, trail 14% below peak
    if gain_from_cost >= runner_trigger_pct:
        dd_from_peak = (peak - current_price) / peak if peak > 0 else 0.0
        if dd_from_peak >= runner_dd_pct:
            return {
                "should_exit": True,
                "action": "BIG_WINNER_TRAIL",
                "reason": f"BIG_WINNER_TRAIL triggered: Dropped {dd_from_peak*100:.1f}% from peak (${peak:.2f}). Securing +{plpc*100:+.2f}% profit."
            }

    # 3. Structural 50-Day SMA Trend Breakdown
    if sma50 is not None and not math.isnan(sma50):
        breakdown_price = sma50 * (1.0 - trend_50sma_buffer_pct)
        if current_price < breakdown_price:
            return {
                "should_exit": True,
                "action": "TREND_50SMA_BREAK",
                "reason": f"TREND_50SMA_BREAK: Price (${current_price:.2f}) < 97.5% of 50-SMA (${sma50:.2f}) [PnL: {plpc*100:+.2f}%]"
            }

    # 4. Healthy momentum holding: Let the runner compound!
    return {
        "should_exit": False,
        "action": "HOLD",
        "reason": f"Momentum intact [PnL: {plpc*100:+.2f}%, Peaked: +{gain_from_cost*100:.1f}%]. Preserving holding."
    }
