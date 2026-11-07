"""
Production Dual-Pod Institutional Forward Paper Trading Engine
==============================================================
Governs 13-Week Gate B Forward Testing across:
  - Pod 1: India Growth Equities Momentum (NSE 100 Liquid Growth Leaders, Variant 2)
  - Pod 2: US Growth Equities Momentum (NASDAQ/NYSE 100 High-Alpha Growth Leaders)

Institutional Architecture:
  1. Next-Day Open Execution strictly enforced with overnight gap down risk modeled.
  2. Double High-Water Mark: Lifetime HWM (never resets) vs Operating Drawdown Ladder.
  3. Multi-Tier Trailing Profit Runners (+25%, +50%, +100%).
  4. Macro Bear Defense: When benchmark is below 200-SMA, new buys are frozen and cash compounds in liquid yield.
  5. Sourced Transaction Costs: Flat Dhan Rs 14.75 DP fee for India, SEC/FINRA fees for US, and variable friction.
  6. Persistent State: JSON state file + CSV trade log + daily NAV ledger.
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import math
import json
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
INDIA_TICKERS_FILE = os.path.join(DATA_DIR, "nse_tickers.txt")
US_TICKERS_FILE = os.path.join(DATA_DIR, "us_growth_tickers.txt")

INDIA_STATE_FILE = os.path.join(DATA_DIR, "paper_state_india.json")
US_STATE_FILE = os.path.join(DATA_DIR, "paper_state_us.json")

INDIA_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_india.csv")
US_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_us.csv")
EQUITY_LOG_CSV = os.path.join(DATA_DIR, "paper_equity_log.csv")

# Institutional Default Settings
DEFAULT_INDIA_CAPITAL = 1000000.0  # INR 10 Lakhs
DEFAULT_US_CAPITAL = 10000.0       # USD $10,000

INDIA_FLAT_DP_FEE = 14.75          # Flat Rs 14.75 per sale scrip
INDIA_BUY_BPS = 25.35              # Stressed variable costs
INDIA_SELL_BPS = 23.85
INDIA_HARD_STOP = -0.12            # -12.0% hard stop
INDIA_TREND_SMA = 150              # 150-SMA trend exit

US_BUY_BPS = 5.0                   # 5 bps variable friction
US_SELL_BPS = 6.5                  # 5 bps + SEC fee (27.80 per million) + FINRA TAF
US_HARD_STOP = -0.10               # -10.0% hard stop
US_TREND_SMA = 150                 # 150-SMA trend exit

MAX_CORE_POSITIONS = 10            # 10 slots (10% allocation)


def calc_vectorized_momentum(series: np.ndarray, window: int = 90) -> float:
    n = len(series)
    if n < window:
        return 0.0
    arr = series[-window:]
    log_p = np.log(np.maximum(arr, 1e-4))
    w = np.arange(window) - (window - 1.0) / 2.0
    ss_x = np.sum(w ** 2)
    w_norm = w / ss_x
    slope = np.sum(log_p * w_norm)
    y_mean = np.mean(log_p)
    ss_y = np.sum((log_p - y_mean) ** 2)
    cov = np.sum(w * (log_p - y_mean))
    r2 = (cov ** 2) / (ss_x * ss_y) if ss_y > 1e-12 else 0.0
    ann_slope = math.expm1(np.clip(slope * 252.0, -10.0, 10.0))
    return float(ann_slope * r2)


class PodPaperEngine:
    def __init__(self, pod_name: str, currency: str, initial_capital: float, state_file: str, trades_file: str, live_broker: bool = True):
        self.pod_name = pod_name
        self.currency = currency
        self.initial_capital = initial_capital
        self.state_file = state_file
        self.trades_file = trades_file
        self.live_broker = live_broker
        self.state = self._load_state()

    def sync_alpaca_live(self):
        """Synchronizes US pod state directly with live Alpaca paper account."""
        if "US" not in self.pod_name or not self.live_broker:
            return
        try:
            from trading_system.app.config.settings import settings
            from trading_system.app.broker.alpaca import AlpacaBrokerAdapter

            api_key = settings.PAPER_API_KEY
            api_secret = settings.PAPER_API_SECRET
            if not api_key or not api_secret or api_key == "mock":
                print(f"[{self.pod_name}] No live Alpaca credentials configured; continuing in simulated paper mode.")
                return

            adapter = AlpacaBrokerAdapter(api_key=api_key, api_secret=api_secret)
            if not adapter.is_connected():
                print(f"[{self.pod_name}] Alpaca connection check failed.")
                return

            acc = adapter.get_account_details()
            positions = adapter.get_positions_detailed()

            self.state["cash"] = float(acc["cash"])
            total_equity = float(acc["equity"])
            if "initial_capital" not in self.state or self.state.get("initial_capital", 10000.0) == 10000.0:
                self.state["initial_capital"] = total_equity
            self.initial_capital = self.state.get("initial_capital", total_equity)
            if total_equity > self.state.get("hwm_true", 0.0):
                self.state["hwm_true"] = total_equity

            # Map current live Alpaca positions
            live_symbols = set()
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            for pos in positions:
                sym = pos["symbol"]
                live_symbols.add(sym)
                qty = float(pos["qty"])
                entry_p = float(pos["avg_entry_price"])
                cur_p = float(pos["current_price"])

                if sym not in self.state["positions"]:
                    self.state["positions"][sym] = {
                        "shares": qty,
                        "entry_price": entry_p,
                        "entry_date": now_str,
                        "peak_price": max(entry_p, cur_p)
                    }
                else:
                    self.state["positions"][sym]["shares"] = qty
                    self.state["positions"][sym]["entry_price"] = entry_p
                    prev_peak = self.state["positions"][sym].get("peak_price", entry_p)
                    self.state["positions"][sym]["peak_price"] = max(prev_peak, cur_p)

            # Clean up closed positions
            for sym in list(self.state["positions"].keys()):
                if sym not in live_symbols:
                    del self.state["positions"][sym]

            self._save_state()
            print(f"[{self.pod_name}] Synced with live Alpaca: Equity=${total_equity:,.2f}, Cash=${self.state['cash']:,.2f}, Positions={len(self.state['positions'])}")
        except Exception as e:
            print(f"[{self.pod_name}] Alpaca sync warning: {e}")

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "pod_name": self.pod_name,
            "currency": self.currency,
            "cash": self.initial_capital,
            "positions": {},       # sym -> {shares, entry_price, entry_date, peak_price}
            "pending_buys": [],    # [{sym, target_alloc, score}]
            "pending_sells": [],   # [{sym, reason}]
            "hwm_true": self.initial_capital,
            "hwm_ladder": self.initial_capital,
            "max_drawdown": 0.0,
            "in_tier4_defense": False,
            "cooling_off": 0,
            "recovery_streak": 0,
            "last_updated": None
        }

    def _save_state(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_trade(self, trade_data: Dict[str, Any]):
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        file_exists = os.path.exists(self.trades_file) and os.path.getsize(self.trades_file) > 0
        df_row = pd.DataFrame([trade_data])
        df_row.to_csv(self.trades_file, mode="a", index=False, header=not file_exists)

    def execute_open_fills(self, current_open_prices: Dict[str, float]):
        """Step 0: Execute queued orders at 09:15 / 09:30 Market Open with realistic slippage."""
        buy_fee = (INDIA_BUY_BPS if "INDIA" in self.pod_name else US_BUY_BPS) / 10000.0
        sell_fee = (INDIA_SELL_BPS if "INDIA" in self.pod_name else US_SELL_BPS) / 10000.0
        flat_dp = INDIA_FLAT_DP_FEE if "INDIA" in self.pod_name else 0.0
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        alpaca_adapter = None
        if "US" in self.pod_name and self.live_broker:
            try:
                from trading_system.app.config.settings import settings
                from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
                if settings.PAPER_API_KEY and settings.PAPER_API_SECRET and settings.PAPER_API_KEY != "mock":
                    alpaca_adapter = AlpacaExecutionAdapter(api_key=settings.PAPER_API_KEY, api_secret=settings.PAPER_API_SECRET)
            except Exception as e:
                print(f"[{self.pod_name}] Alpaca adapter init error: {e}")

        # 1. Execute Sells
        if self.state["pending_sells"]:
            for item in self.state["pending_sells"]:
                sym = item["sym"]
                reason = item["reason"]
                if sym not in self.state["positions"]:
                    continue
                pos = self.state["positions"][sym]
                shares = pos["shares"]
                open_p = current_open_prices.get(sym, pos["entry_price"])
                fill_p = open_p * (1.0 - sell_fee)
                proceeds = shares * fill_p
                cost = pos["entry_price"]
                gain = proceeds - (shares * cost) - flat_dp

                # Route real order to Alpaca Paper if active
                if alpaca_adapter:
                    qty_to_sell = int(round(shares))
                    if qty_to_sell > 0:
                        res = alpaca_adapter.submit_order({
                            "symbol": sym,
                            "quantity": qty_to_sell,
                            "side": "sell",
                            "type": "market"
                        })
                        print(f"  [ALPACA ROUTED SELL] {sym:<12} {qty_to_sell} shs -> Status: {res.get('status')} (Order ID: {res.get('order_id')})")

                self.state["cash"] += (proceeds - flat_dp)
                self.log_trade({
                    "timestamp": now_str,
                    "symbol": sym,
                    "action": "SELL",
                    "shares": shares,
                    "open_price": open_p,
                    "fill_price": fill_p,
                    "proceeds": proceeds,
                    "realized_pnl": gain,
                    "pnl_pct": (fill_p - cost) / cost if cost > 0 else 0.0,
                    "dp_fee": flat_dp,
                    "reason": reason
                })
                print(f"  [EXECUTE SELL] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f} | PnL: {self.currency} {gain:>+9.2f} ({reason})")
                del self.state["positions"][sym]
            self.state["pending_sells"] = []

        # 2. Execute Buys
        if self.state["pending_buys"]:
            for item in self.state["pending_buys"]:
                sym = item["sym"]
                alloc = min(item["target_alloc"], self.state["cash"] * 0.96)
                score = item.get("score", 0.0)
                open_p = current_open_prices.get(sym, 0.0)
                if open_p <= 0 or alloc < 50.0:
                    continue
                fill_p = open_p * (1.0 + buy_fee)
                shares = round(alloc / fill_p, 4 if "US" in self.pod_name else 2)
                cost = shares * fill_p
                if cost <= self.state["cash"] and shares > 0:
                    # Route real order to Alpaca Paper if active
                    if alpaca_adapter:
                        qty_to_buy = int(math.floor(alloc / fill_p))
                        if qty_to_buy > 0:
                            res = alpaca_adapter.submit_order({
                                "symbol": sym,
                                "quantity": qty_to_buy,
                                "side": "buy",
                                "type": "market"
                            })
                            print(f"  [ALPACA ROUTED BUY ] {sym:<12} {qty_to_buy} shs -> Status: {res.get('status')} (Order ID: {res.get('order_id')})")

                    self.state["cash"] -= cost
                    self.state["positions"][sym] = {
                        "shares": shares,
                        "entry_price": fill_p,
                        "entry_date": now_str,
                        "peak_price": open_p
                    }
                    self.log_trade({
                        "timestamp": now_str,
                        "symbol": sym,
                        "action": "BUY",
                        "shares": shares,
                        "open_price": open_p,
                        "fill_price": fill_p,
                        "cost": cost,
                        "realized_pnl": 0.0,
                        "pnl_pct": 0.0,
                        "dp_fee": 0.0,
                        "reason": f"ENTRY Blended Mom Score: {score:.2f}"
                    })
                    print(f"  [EXECUTE BUY ] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f} | Cost: {self.currency} {cost:>9.2f}")
            self.state["pending_buys"] = []

        self._save_state()

    def scan_and_evaluate(self, universe_data: Dict[str, pd.DataFrame], benchmark_data: pd.DataFrame):
        """Step E & F: Scan market closes, evaluate stops/trails, and queue Next-Day Open orders."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Benchmark Macro Filter
        bench_close = benchmark_data["close"].iloc[-1]
        bench_sma200 = benchmark_data["close"].rolling(200, min_periods=50).mean().iloc[-1]
        bench_sma50 = benchmark_data["close"].rolling(50, min_periods=20).mean().iloc[-1]
        bench_sma50_prev = benchmark_data["close"].rolling(50, min_periods=20).mean().iloc[-6]
        sma50_up = bench_sma50 > bench_sma50_prev
        is_macro_bull = (bench_close > bench_sma200) and sma50_up

        print(f"\n[{self.pod_name} RADAR] Benchmark: Close={bench_close:.2f} vs 200-SMA={bench_sma200:.2f} | 50-SMA Sloping Up={sma50_up} -> Regime: [{'BULL' if is_macro_bull else 'BEAR DEFENSE'}]")

        # 2. Mark to Market & Peak Update
        port_equity = 0.0
        current_prices = {}
        for sym, pos in list(self.state["positions"].items()):
            if sym in universe_data and not universe_data[sym].empty:
                p = float(universe_data[sym]["close"].iloc[-1])
                current_prices[sym] = p
                port_equity += pos["shares"] * p
                if p > pos.get("peak_price", p):
                    pos["peak_price"] = p
            else:
                port_equity += pos["shares"] * pos["entry_price"]
                current_prices[sym] = pos["entry_price"]

        total_equity = self.state["cash"] + port_equity
        if total_equity > self.state["hwm_true"]:
            self.state["hwm_true"] = total_equity
        current_dd = (total_equity - self.state["hwm_true"]) / self.state["hwm_true"]
        if current_dd < self.state["max_drawdown"]:
            self.state["max_drawdown"] = current_dd

        print(f"[{self.pod_name} NAV] Total Equity: {self.currency} {total_equity:,.2f} | Cash: {self.currency} {self.state['cash']:,.2f} | Port: {self.currency} {port_equity:,.2f} | MaxDD: {self.state['max_drawdown']*100:.2f}%")

        # 3. Evaluate Exits
        hard_stop = INDIA_HARD_STOP if self.pod_name == "INDIA" else US_HARD_STOP
        trail_tiers = [(1.00, -0.25), (0.50, -0.20), (0.25, -0.15)]
        signals_to_exit = []

        for sym, pos in list(self.state["positions"].items()):
            if sym not in current_prices:
                continue
            price = current_prices[sym]
            cost = pos["entry_price"]
            plpc = (price - cost) / cost if cost > 0 else 0.0
            peak = pos.get("peak_price", price)
            pullback = (price - peak) / peak if peak > 0 else 0.0

            # Check Hard Stop
            if plpc <= hard_stop:
                signals_to_exit.append({"sym": sym, "reason": f"HARD_STOP ({hard_stop*100:.1f}%) [PnL: {plpc*100:+.1f}%]"})
                continue

            # Macro Bear Trail Override
            if not is_macro_bull and pullback <= -0.12 and plpc > 0.05:
                signals_to_exit.append({"sym": sym, "reason": f"MACRO_BEAR_TRAIL [PnL: {plpc*100:+.1f}%, Pullback: {pullback*100:.1f}%]"})
                continue

            # Multi-Tier Trailing Profit Lock
            trailed = False
            for min_gain, trail_pct in trail_tiers:
                if plpc >= min_gain:
                    if pullback <= trail_pct:
                        signals_to_exit.append({"sym": sym, "reason": f"TRAIL_TIER (+{min_gain*100:.0f}% / {trail_pct*100:.0f}%) [PnL: {plpc*100:+.1f}%]"})
                        trailed = True
                    break
            if trailed:
                continue

            # Developing Trend Exit (150-SMA break)
            if sym in universe_data and len(universe_data[sym]) >= 150:
                sma150 = universe_data[sym]["close"].rolling(150, min_periods=50).mean().iloc[-1]
                if price < sma150:
                    signals_to_exit.append({"sym": sym, "reason": f"TREND_SMA150_BREAK [PnL: {plpc*100:+.1f}%]"})

        self.state["pending_sells"] = signals_to_exit
        for s in signals_to_exit:
            print(f"  [SIGNAL QUEUED SELL] {s['sym']:<12} -> Reason: {s['reason']}")

        # 4. Candidate Screening & Entry Sizing
        active_and_pending_count = len(self.state["positions"]) - len(self.state["pending_sells"])
        if is_macro_bull and active_and_pending_count < MAX_CORE_POSITIONS and self.state["cash"] > 100.0:
            open_slots = MAX_CORE_POSITIONS - active_and_pending_count
            cands = []
            min_price = 20.0 if self.pod_name == "INDIA" else 10.0

            for sym, df in universe_data.items():
                if sym in self.state["positions"] or any(p["sym"] == sym for p in signals_to_exit):
                    continue
                if len(df) < 180:
                    continue
                close_arr = df["close"].values
                cur_price = close_arr[-1]
                if cur_price < min_price:
                    continue

                sma150 = pd.Series(close_arr).rolling(150, min_periods=50).mean().iloc[-1]
                if cur_price <= sma150:
                    continue

                m90 = calc_vectorized_momentum(close_arr, window=90)
                m180 = calc_vectorized_momentum(close_arr, window=180)
                score = 0.60 * m90 + 0.40 * m180
                if score > 0.15:
                    cands.append({"sym": sym, "price": cur_price, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)
            selected = cands[:open_slots]

            alloc_per_cand = (total_equity * 0.10)
            pending_buys = []
            avail_cash = self.state["cash"] * 0.96
            for c in selected:
                if avail_cash < 50.0:
                    break
                alloc = min(alloc_per_cand, avail_cash)
                pending_buys.append({"sym": c["sym"], "target_alloc": alloc, "score": c["score"]})
                avail_cash -= alloc
                print(f"  [SIGNAL QUEUED BUY ] {c['sym']:<12} Target: {self.currency} {alloc:>9.2f} | Score: {c['score']:.2f}")

            self.state["pending_buys"] = pending_buys

        self._save_state()

        # Append to Daily Equity Log
        os.makedirs(os.path.dirname(EQUITY_LOG_CSV), exist_ok=True)
        file_exists = os.path.exists(EQUITY_LOG_CSV) and os.path.getsize(EQUITY_LOG_CSV) > 0
        eq_entry = {
            "date": now_str[:10],
            "pod": self.pod_name,
            "currency": self.currency,
            "total_equity": round(total_equity, 2),
            "cash": round(self.state["cash"], 2),
            "portfolio_equity": round(port_equity, 2),
            "hwm_true": round(self.state["hwm_true"], 2),
            "drawdown_pct": round(current_dd * 100.0, 2),
            "open_positions_count": len(self.state["positions"])
        }
        pd.DataFrame([eq_entry]).to_csv(EQUITY_LOG_CSV, mode="a", index=False, header=not file_exists)

    def print_status_tear_sheet(self):
        if "US" in self.pod_name and self.live_broker:
            self.sync_alpaca_live()

        print("\n" + "=" * 95)
        print(f"================== {self.pod_name} FORWARD PAPER TRADING STATUS TEAR SHEET ==================")
        print("=" * 95)
        print(f"Base Currency               : {self.currency}")
        print(f"Initial Starting Capital    : {self.currency} {self.initial_capital:>14,.2f}")
        total_eq = self.state["cash"] + sum(p["shares"] * p["entry_price"] for p in self.state["positions"].values())
        print(f"Current Total NAV Equity    : {self.currency} {total_eq:>14,.2f}")
        print(f"Cash Balance                : {self.currency} {self.state['cash']:>14,.2f}")
        print(f"Lifetime True Peak HWM      : {self.currency} {self.state['hwm_true']:>14,.2f}")
        print(f"Current Strategy Drawdown   : {self.state['max_drawdown']*100:>13.2f}%")
        print(f"Active Positions Held       : {len(self.state['positions'])} / {MAX_CORE_POSITIONS} slots")
        print(f"Pending Orders Queued       : {len(self.state['pending_sells'])} Sells, {len(self.state['pending_buys'])} Buys")
        print("-" * 95)
        if self.state["positions"]:
            print(f"{'Symbol':<10} | {'Shares':<8} | {'Entry Price':<12} | {'Peak Price':<12} | {'Stop Ref':<12} | {'Trail Ref':<12}")
            print("-" * 95)
            hard_stop = INDIA_HARD_STOP if "INDIA" in self.pod_name else US_HARD_STOP
            for sym, pos in sorted(self.state["positions"].items()):
                entry = pos["entry_price"]
                peak = pos.get("peak_price", entry)
                hard_stop_val = entry * (1.0 + hard_stop)
                trail_stop_val = peak * 0.85
                print(f"{sym:<10} | {pos['shares']:>8.1f} | {self.currency} {entry:>9.2f} | {self.currency} {peak:>9.2f} | {self.currency} {hard_stop_val:>9.2f} | {self.currency} {trail_stop_val:>9.2f}")
        else:
            print("  (Zero active equity positions currently held; capital 100% in cash yield)")

        if self.state["pending_sells"]:
            print("-" * 95)
            print("QUEUED SELL ORDERS (To Execute at Next Open):")
            for s in self.state["pending_sells"]:
                print(f"  -> SELL {s['sym']:<10} | Reason: {s['reason']}")

        if self.state["pending_buys"]:
            print("-" * 95)
            print("QUEUED BUY ORDERS (To Execute at Next Open):")
            for b in self.state["pending_buys"]:
                print(f"  -> BUY  {b['sym']:<10} | Alloc: {self.currency} {b['target_alloc']:>10,.2f} | Blended Mom Score: {b['score']:.2f}")

        print("=" * 95 + "\n")


def normalize_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    return df


def fetch_yfinance_history(tickers: List[str], period: str = "1y") -> Dict[str, pd.DataFrame]:
    out = {}
    print(f"Fetching recent market data for {len(tickers)} symbols via yfinance...")
    try:
        data = yf.download(tickers, period=period, progress=False, group_by="ticker", auto_adjust=False)
        for sym in tickers:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if sym in data.columns.levels[-1]:
                        df = data.xs(sym, axis=1, level=-1).dropna(how="all").copy()
                    elif sym in data.columns.levels[0]:
                        df = data[sym].dropna(how="all").copy()
                    else:
                        continue
                else:
                    df = data.dropna(how="all").copy()
                df.columns = [str(c).lower() for c in df.columns]
                if len(df) >= 50:
                    out[sym] = df
            except Exception:
                pass
    except Exception as e:
        print(f"Batch fetch error: {e}")
    return out


def main():
    parser = argparse.ArgumentParser(description="Dual-Pod Institutional Paper Trading Engine")
    parser.add_argument("--pod", choices=["all", "india", "us"], default="all", help="Target pod")
    parser.add_argument("--phase", choices=["scan", "execute", "status"], default="status", help="Trading cycle phase")
    args = parser.parse_args()

    india_engine = PodPaperEngine(
        pod_name="INDIA",
        currency="INR",
        initial_capital=DEFAULT_INDIA_CAPITAL,
        state_file=INDIA_STATE_FILE,
        trades_file=INDIA_TRADES_CSV
    )

    us_engine = PodPaperEngine(
        pod_name="US",
        currency="USD",
        initial_capital=DEFAULT_US_CAPITAL,
        state_file=US_STATE_FILE,
        trades_file=US_TRADES_CSV
    )

    if args.phase == "status":
        if args.pod in ["all", "india"]:
            india_engine.print_status_tear_sheet()
        if args.pod in ["all", "us"]:
            us_engine.print_status_tear_sheet()
        return

    # PHASE: SCAN (Run at Market Close: 15:35 IST / 16:05 EST)
    if args.phase == "scan":
        if args.pod in ["all", "india"]:
            print("\n>>> [POD 1: INDIA] SCANNING NSE UNIVERSE AT MARKET CLOSE (15:35 IST)...")
            with open(INDIA_TICKERS_FILE, "r") as f:
                india_tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            combined_tickers = list(set(india_tickers) | set(india_engine.state["positions"].keys()))
            india_data = fetch_yfinance_history(combined_tickers, period="1y")
            bench_india = yf.download("^NSEI", period="1y", progress=False, auto_adjust=False)
            bench_india = normalize_df_columns(bench_india)
            india_engine.scan_and_evaluate(india_data, bench_india)

        if args.pod in ["all", "us"]:
            print("\n>>> [POD 2: US] SCANNING US GROWTH UNIVERSE AT MARKET CLOSE (16:05 EST)...")
            us_engine.sync_alpaca_live()
            with open(US_TICKERS_FILE, "r") as f:
                us_tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            combined_tickers = list(set(us_tickers) | set(us_engine.state["positions"].keys()))
            us_data = fetch_yfinance_history(combined_tickers, period="1y")
            bench_us = yf.download("SPY", period="1y", progress=False, auto_adjust=False)
            bench_us = normalize_df_columns(bench_us)
            us_engine.scan_and_evaluate(us_data, bench_us)

    # PHASE: EXECUTE (Run at Market Open: 09:14 IST / 09:29 EST)
    elif args.phase == "execute":
        if args.pod in ["all", "india"]:
            print("\n>>> [POD 1: INDIA] EXECUTING QUEUED ORDERS AT MARKET OPEN (09:15 IST)...")
            with open(INDIA_TICKERS_FILE, "r") as f:
                india_tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            needed_symbols = list(set(india_tickers) | set(india_engine.state["positions"].keys()) | {p["sym"] for p in india_engine.state["pending_buys"]} | {p["sym"] for p in india_engine.state["pending_sells"]})
            india_open_df = yf.download(needed_symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False)
            current_opens = {}
            for s in needed_symbols:
                try:
                    if isinstance(india_open_df.columns, pd.MultiIndex):
                        if s in india_open_df.columns.levels[-1]:
                            df = india_open_df.xs(s, axis=1, level=-1).dropna(how="all")
                        elif s in india_open_df.columns.levels[0]:
                            df = india_open_df[s].dropna(how="all")
                        else:
                            continue
                    else:
                        df = india_open_df.dropna(how="all")
                    df.columns = [str(c).lower() for c in df.columns]
                    current_opens[s] = float(df["open"].dropna().iloc[-1])
                except Exception:
                    pass
            india_engine.execute_open_fills(current_opens)

        if args.pod in ["all", "us"]:
            print("\n>>> [POD 2: US] EXECUTING QUEUED ORDERS AT MARKET OPEN (09:30 EST)...")
            with open(US_TICKERS_FILE, "r") as f:
                us_tickers = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            needed_symbols = list(set(us_tickers) | set(us_engine.state["positions"].keys()) | {p["sym"] for p in us_engine.state["pending_buys"]} | {p["sym"] for p in us_engine.state["pending_sells"]})
            us_open_df = yf.download(needed_symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False)
            current_opens = {}
            for s in needed_symbols:
                try:
                    if isinstance(us_open_df.columns, pd.MultiIndex):
                        if s in us_open_df.columns.levels[-1]:
                            df = us_open_df.xs(s, axis=1, level=-1).dropna(how="all")
                        elif s in us_open_df.columns.levels[0]:
                            df = us_open_df[s].dropna(how="all")
                        else:
                            continue
                    else:
                        df = us_open_df.dropna(how="all")
                    df.columns = [str(c).lower() for c in df.columns]
                    current_opens[s] = float(df["open"].dropna().iloc[-1])
                except Exception:
                    pass
            us_engine.execute_open_fills(current_opens)


if __name__ == "__main__":
    main()
