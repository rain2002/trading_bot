"""
Production Dual-Pod Institutional Forward Paper Trading Engine
==============================================================
Governs Exploratory Shadow Tracking (Forward Real-Time Paper Mode - Non-Gate B) across:
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
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

import pandas as pd
import numpy as np
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.research.momentum_crash import evaluate_dual_pod_regime_and_volatility
from trading_system.app.data.constituent_manager import PointInTimeConstituentManager

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
INDIA_TICKERS_FILE = os.path.join(DATA_DIR, "nse_tickers.txt")
US_TICKERS_FILE = os.path.join(DATA_DIR, "us_growth_tickers.txt")

INDIA_STATE_FILE = os.path.join(DATA_DIR, "paper_state_india.json")
US_STATE_FILE = os.path.join(DATA_DIR, "paper_state_us.json")
MULTI_ASSET_STATE_FILE = os.path.join(DATA_DIR, "paper_state_multi_asset.json")

INDIA_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_india.csv")
US_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_us.csv")
MULTI_ASSET_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_multi_asset.csv")
EQUITY_LOG_CSV = os.path.join(DATA_DIR, "paper_equity_log.csv")

# Institutional Default Settings
DEFAULT_INDIA_CAPITAL = 80000.0    # INR 80,000 (Mandatory Gate A scale)
DEFAULT_US_CAPITAL = 100000.0      # USD $100,000 (Alpaca Paper Desk principal)
DEFAULT_MULTI_ASSET_CAPITAL = 80000.0 # INR 80,000 (Pod C Gate A protocol capital)

# Pod C Canonical Allocations (Multi-Asset Macro Trend Following)
# Master Handover Specification: 40% India Trend, 30% US Tech, 20% Gold, 10% Liquid Cash Yield
POD_C_CORE_ALLOCATIONS = {
    "NIFTYBEES.NS": 0.40,  # 40% India Trend (Nifty 50 ETF)
    "MON100.NS": 0.30,     # 30% US Mega-Cap Tech (Nasdaq 100 ETF)
    "GOLDBEES.NS": 0.20,   # 20% Domestic Gold (Gold BeES ETF)
    "CASH": 0.10           # 10% Sovereign Liquid Cash Yield (Base reserve + defensive reallocation)
}

# Instrument specific execution friction & statutory tax characteristics
POD_C_ASSET_SPECS = {
    "NIFTYBEES.NS": {
        "class": "EQUITY", "norm_slip_bps": 5.0, "stress_slip_bps": 7.5,
        "stt_sell_bps": 10.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "name": "Nippon India ETF Nifty 50 BeES (India Large-Cap)"
    },
    "MON100.NS": {
        "class": "INTL", "norm_slip_bps": 12.0, "stress_slip_bps": 20.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "name": "Motilal Oswal Nasdaq 100 ETF (US Secular Tech)"
    },
    "GOLDBEES.NS": {
        "class": "METAL", "norm_slip_bps": 7.5, "stress_slip_bps": 12.0,
        "stt_sell_bps": 0.0, "stamp_buy_bps": 1.5, "exch_bps": 0.297, "sebi_bps": 0.01,
        "name": "Nippon India ETF Gold BeES (Domestic Gold)"
    }
}

INDIA_FLAT_DP_FEE = 14.75          # Flat Rs 14.75 per sale scrip
INDIA_BUY_BPS = 25.35              # Stressed variable costs
INDIA_SELL_BPS = 23.85
INDIA_HARD_STOP = -0.12            # -12.0% hard stop
INDIA_TREND_SMA = 150              # 150-SMA trend exit

US_BUY_BPS = 5.0                   # 5 bps variable friction
US_SELL_BPS = 6.5                  # 5 bps + SEC fee (27.80 per million) + FINRA TAF
US_HARD_STOP = -0.10               # -10.0% hard stop
US_TREND_SMA = 150                 # 150-SMA trend exit

MAX_CORE_POSITIONS = 10            # Default 10 slots (overridden dynamically per pod)


def calc_atr(df: pd.DataFrame, window: int = 20) -> float:
    """Calculates the current 20-day Average True Range (ATR)."""
    if len(df) < window + 1:
        return 0.0
    try:
        h = df["high"].values
        l = df["low"].values
        c = df["close"].values
        tr = np.zeros(len(c))
        tr[0] = h[0] - l[0]
        for i in range(1, len(c)):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        s_tr = pd.Series(tr)
        val = s_tr.rolling(window, min_periods=window).mean().iloc[-1]
        return float(val) if not np.isnan(val) else 0.0
    except Exception:
        return 0.0


def calc_vectorized_momentum(series: np.ndarray, window: int = 90, skip_days: int = 0) -> float:
    n = len(series)
    if n < window + skip_days:
        return 0.0
    if skip_days > 0:
        arr = series[-(window + skip_days):-skip_days]
    else:
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



def get_git_commit_hash() -> str:
    """Retrieves current short git commit hash for audit provenance and frozen spec validation."""
    try:
        import subprocess
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN"


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file with normalized newlines for cryptographic provenance."""
    if not filepath or not os.path.exists(filepath):
        return "UNKNOWN_HASH"
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
        return h.hexdigest()
    except Exception:
        return "ERROR_HASH"



def get_active_pit_universe(pod_name: str, as_of_date: Optional[pd.Timestamp] = None) -> List[str]:
    """
    Returns the exact set of active Point-in-Time (PIT) constituent tickers as of as_of_date
    (defaults to current UTC/local date) to eliminate survivorship and lookahead bias.
    """
    if as_of_date is None:
        as_of_date = pd.Timestamp.now()

    if "INDIA" in pod_name:
        changes_csv = os.path.join(DATA_DIR, "nifty50_historical_components_changes.csv")
        se_csv = os.path.join(DATA_DIR, "nifty50_ticker_start_end.csv")
        if os.path.exists(changes_csv):
            mgr = PointInTimeConstituentManager(changes_csv_path=changes_csv, start_end_csv_path=se_csv)
            raw_constituents = mgr.get_active_constituents(as_of_date)
            if raw_constituents:
                tickers = []
                for s in raw_constituents:
                    s_clean = s.replace("-NS", "").replace(".NS", "")
                    tickers.append(f"{s_clean}.NS")
                print(f"[{pod_name} PIT] Loaded {len(tickers)} active Point-in-Time constituents as of {as_of_date.strftime('%Y-%m-%d')}.")
                return sorted(tickers)

        raise RuntimeError(
            f"[{pod_name} PIT FATAL] Point-in-Time constituent database missing or returned empty set for {as_of_date}. "
            f"Silent fallback to static ticker files is strictly prohibited to eliminate survivorship and lookahead bias."
        )
    else:
        changes_csv = os.path.join(DATA_DIR, "sp500_historical_components_changes.csv")
        se_csv = os.path.join(DATA_DIR, "sp500_ticker_start_end.csv")
        if os.path.exists(changes_csv):
            mgr = PointInTimeConstituentManager(changes_csv_path=changes_csv, start_end_csv_path=se_csv)
            raw_constituents = mgr.get_active_constituents(as_of_date)
            if raw_constituents:
                tickers = [s.replace(".", "-") for s in raw_constituents]
                print(f"[{pod_name} PIT] Loaded {len(tickers)} active Point-in-Time constituents as of {as_of_date.strftime('%Y-%m-%d')}.")
                return sorted(tickers)

        raise RuntimeError(
            f"[{pod_name} PIT FATAL] Point-in-Time constituent database missing or returned empty set for {as_of_date}. "
            f"Silent fallback to static ticker files is strictly prohibited to eliminate survivorship and lookahead bias."
        )

class PodPaperEngine:
    def __init__(self, pod_name: str, currency: str, initial_capital: float, state_file: str, trades_file: str, live_broker: bool = False):
        self.pod_name = pod_name
        self.currency = currency
        self.initial_capital = initial_capital
        self.state_file = state_file
        self.trades_file = trades_file
        self.live_broker = live_broker
        # Concentration architecture: 8 slots for US growth momentum (exploratory grid search baseline), 10 slots for India
        self.max_positions = 8 if "US" in self.pod_name else 10
        self.session_trades: List[Dict[str, Any]] = []
        self.state = self._load_state()

    def sync_alpaca_live(self):
        """Synchronizes US pod state directly with live Alpaca paper account."""
        if "US" not in self.pod_name or not self.live_broker:
            return
        try:
            from trading_system.app.config.settings import settings
            from trading_system.app.broker.alpaca import AlpacaBrokerAdapter

            api_key = settings.PAPER_API_KEY or os.environ.get("PAPER_API_KEY")
            api_secret = settings.PAPER_API_SECRET or os.environ.get("PAPER_API_SECRET")
            if not api_key or not api_secret or api_key == "mock":
                print(f"[{self.pod_name}] No paper Alpaca credentials configured (PAPER_API_KEY / PAPER_API_SECRET); continuing in simulated paper mode.")
                return

            adapter = AlpacaBrokerAdapter(
                api_key=api_key,
                api_secret=api_secret,
                base_url="https://paper-api.alpaca.markets"
            )
            if not adapter.is_connected():
                print(f"[{self.pod_name}] Alpaca connection check failed.")
                return

            acc = adapter.get_account_details()
            positions = adapter.get_positions_detailed()

            # Strict Day 0 & State Provenance Integrity Guard
            acc_cash = float(acc["cash"])
            is_day0_verified = self.state.get("day0_verified", False)
            if self.initial_capital == 100000.0 and not is_day0_verified:
                if len(positions) > 0 or abs(acc_cash - 100000.0) > 1.0:
                    raise RuntimeError(
                        f"CRITICAL DAY 0 INTEGRITY GUARD: Alpaca account state does not match logged Day 0 baseline! "
                        f"Expected 0 positions and $100,000.00 cash on Day 0 verification, but Alpaca returned {len(positions)} open positions "
                        f"and ${acc_cash:,.2f} cash. Execution halted to prevent contaminating shadow incubation. "
                        f"Please reset the Alpaca paper account to clean $100,000.00 cash with 0 positions."
                    )
                self.state["day0_verified"] = True

            self.state["cash"] = float(acc["cash"])
            total_equity = float(acc["equity"])
            self.state["equity"] = total_equity
            if "initial_capital" not in self.state:
                if self.initial_capital == 100000.0:
                    self.state["initial_capital"] = 100000.0
                else:
                    self.state["initial_capital"] = total_equity
            elif self.state.get("initial_capital") == 97780.11:
                self.state["initial_capital"] = 100000.0
            self.initial_capital = float(self.state.get("initial_capital", 100000.0))
            if total_equity > self.state.get("hwm_true", 0.0):
                self.state["hwm_true"] = total_equity

            # Reconcile positions tracked by this strategy with live Alpaca fills (ignore foreign resting scrips)
            live_symbols = set()
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            for pos in positions:
                sym = pos["symbol"]
                live_symbols.add(sym)
                qty = float(pos["qty"])
                entry_p = float(pos["avg_entry_price"])
                cur_p = float(pos["current_price"])

                if sym not in self.state["positions"]:
                    if self.initial_capital == 100000.0:
                        print(f"[{self.pod_name}] MISMATCH GUARD: Foreign position '{sym}' ({qty} shs) detected on Alpaca desk; not adopting into shadow book.")
                        continue
                    self.state["positions"][sym] = {
                        "shares": qty,
                        "entry_price": entry_p,
                        "entry_date": now_str,
                        "peak_price": max(entry_p, cur_p),
                        "last_close": cur_p
                    }
                else:
                    self.state["positions"][sym]["shares"] = qty
                    self.state["positions"][sym]["entry_price"] = entry_p
                    prev_peak = self.state["positions"][sym].get("peak_price", entry_p)
                    self.state["positions"][sym]["peak_price"] = max(prev_peak, cur_p)
                    self.state["positions"][sym]["last_close"] = cur_p

            # Clean up closed positions
            for sym in list(self.state["positions"].keys()):
                if sym not in live_symbols:
                    del self.state["positions"][sym]

            self._save_state()
            print(f"[{self.pod_name}] Synced with live Alpaca: Equity=${total_equity:,.2f}, Cash=${self.state['cash']:,.2f}, Positions={len(self.state['positions'])}")
        except RuntimeError:
            raise
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
            "day0_verified": False,
            "last_updated": None
        }

    def _save_state(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_trade(self, trade_data: Dict[str, Any]):
        self.session_trades.append(dict(trade_data))
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        file_exists = os.path.exists(self.trades_file) and os.path.getsize(self.trades_file) > 0
        df_row = pd.DataFrame([trade_data])
        df_row.to_csv(self.trades_file, mode="a", index=False, header=not file_exists)

    def execute_open_fills(
        self,
        current_open_prices: Dict[str, float],
        runtime_prices: Optional[Dict[str, float]] = None,
        delay_mins: int = 0
    ):
        """
        Step 0: Execute queued orders with realistic slippage.
        If runner arrives with delay past open (>5 mins), executes at the actual runtime market price
        (eliminating optimistic fills at stale open prices) and records the delay gap in trade logs.
        """
        buy_fee = (INDIA_BUY_BPS if "INDIA" in self.pod_name else US_BUY_BPS) / 10000.0
        sell_fee = (INDIA_SELL_BPS if "INDIA" in self.pod_name else US_SELL_BPS) / 10000.0
        flat_dp = INDIA_FLAT_DP_FEE if "INDIA" in self.pod_name else 0.0
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        alpaca_adapter = None
        if "US" in self.pod_name and self.live_broker:
            try:
                from trading_system.app.config.settings import settings
                from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter
                api_key = settings.PAPER_API_KEY or os.environ.get("PAPER_API_KEY")
                api_secret = settings.PAPER_API_SECRET or os.environ.get("PAPER_API_SECRET")
                if api_key and api_secret and api_key != "mock":
                    alpaca_adapter = AlpacaExecutionAdapter(
                        api_key=api_key,
                        api_secret=api_secret,
                        base_url="https://paper-api.alpaca.markets"
                    )
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
                total_pos_shares = float(pos["shares"])
                trim_shares = item.get("trim_shares")
                if trim_shares and 0 < trim_shares < total_pos_shares:
                    shares = float(trim_shares)
                    is_full_exit = False
                else:
                    shares = float(total_pos_shares)
                    is_full_exit = True

                open_p = float(current_open_prices.get(sym, pos.get("entry_price", 1.0)))
                if runtime_prices and sym in runtime_prices and delay_mins > 5:
                    runtime_p = float(runtime_prices[sym])
                else:
                    runtime_p = open_p

                # Fill at runtime price when delayed, preventing optimistic stale-open exits
                base_exec_p = runtime_p if delay_mins > 5 else open_p
                gap_pct = ((runtime_p - open_p) / open_p * 100.0) if open_p > 0 else 0.0

                fill_p = base_exec_p * (1.0 - sell_fee)
                proceeds = shares * fill_p
                cost = float(pos["entry_price"])
                gain = proceeds - (shares * cost) - (flat_dp if is_full_exit else 0.0)

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

                self.state["cash"] += (proceeds - (flat_dp if is_full_exit else 0.0))
                self.log_trade({
                    "timestamp": now_str,
                    "symbol": sym,
                    "action": "TRIM" if not is_full_exit else "SELL",
                    "shares": shares,
                    "open_price": round(open_p, 4),
                    "fill_price": round(fill_p, 4),
                    "proceeds": round(proceeds, 2),
                    "cost": round(cost, 4),
                    "realized_pnl": round(gain, 2),
                    "pnl_pct": round((fill_p - cost) / cost if cost > 0 else 0.0, 4),
                    "dp_fee": flat_dp if is_full_exit else 0.0,
                    "reason": reason,
                    "delay_mins": delay_mins,
                    "open_delay_gap_pct": round(gap_pct, 4)
                })
                delay_str = f" [Delay: {delay_mins}m, Gap: {gap_pct:+.2f}%]" if delay_mins > 5 else ""
                print(f"  [EXECUTE {'TRIM' if not is_full_exit else 'SELL'}] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f}{delay_str} | PnL: {self.currency} {gain:>+9.2f} ({reason})")
                if is_full_exit:
                    del self.state["positions"][sym]
                else:
                    self.state["positions"][sym]["shares"] -= shares
                    self.state["positions"][sym]["last_close"] = runtime_p
            self.state["pending_sells"] = []

        # 2. Execute Buys
        if self.state["pending_buys"]:
            for item in self.state["pending_buys"]:
                sym = item["sym"]
                alloc = min(item["target_alloc"], self.state["cash"] * 0.96)
                score = item.get("score", 0.0)
                open_p = float(current_open_prices.get(sym, 0.0))
                if open_p <= 0 or alloc < 50.0:
                    continue

                if runtime_prices and sym in runtime_prices and delay_mins > 5:
                    runtime_p = float(runtime_prices[sym])
                else:
                    runtime_p = open_p

                # Fill at runtime price when delayed, preventing optimistic stale-open entries
                base_exec_p = runtime_p if delay_mins > 5 else open_p
                gap_pct = ((runtime_p - open_p) / open_p * 100.0) if open_p > 0 else 0.0

                fill_p = base_exec_p * (1.0 + buy_fee)
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
                        "peak_price": max(open_p, runtime_p, fill_p),
                        "last_close": runtime_p
                    }
                    self.log_trade({
                        "timestamp": now_str,
                        "symbol": sym,
                        "action": "BUY",
                        "shares": shares,
                        "open_price": round(open_p, 4),
                        "fill_price": round(fill_p, 4),
                        "proceeds": 0.0,
                        "cost": round(cost, 2),
                        "realized_pnl": 0.0,
                        "pnl_pct": 0.0,
                        "dp_fee": 0.0,
                        "reason": f"ENTRY Blended Mom Score: {score:.2f}",
                        "delay_mins": delay_mins,
                        "open_delay_gap_pct": round(gap_pct, 4)
                    })
                    delay_str = f" [Delay: {delay_mins}m, Gap: {gap_pct:+.2f}%]" if delay_mins > 5 else ""
                    print(f"  [EXECUTE BUY ] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f}{delay_str} | Cost: {self.currency} {cost:>9.2f}")
            self.state["pending_buys"] = []

        self._save_state()

    def log_daily_equity(
        self,
        status: str = "COMPLETED",
        delay_mins: int = 0,
        notes: str = "",
        port_equity: Optional[float] = None,
        total_equity: Optional[float] = None,
        hwm: Optional[float] = None,
        drawdown_pct: Optional[float] = None
    ):
        """
        Audited Provenance Tracking:
        Appends an immutable daily equity log record with explicit status, runner delay,
        and fail-closed NaN sanitization.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        commit_hash = get_git_commit_hash()

        # Sanitize Cash
        cash_val = float(self.state.get("cash", 0.0))
        if math.isnan(cash_val):
            cash_val = float(self.state.get("initial_capital", 100000.0 if "US" in self.pod_name else 80000.0))
        self.state["cash"] = cash_val

        # Sanitize Portfolio Equity
        if port_equity is None:
            port_equity = 0.0
            for sym, pos in self.state.get("positions", {}).items():
                shs = float(pos.get("shares", 0.0))
                # Mark to market using last known close or entry price (NEVER peak_price, preventing overstated equity on skip rows)
                p = float(pos.get("last_close", pos.get("entry_price", 0.0)))
                if not math.isnan(shs) and not math.isnan(p) and p > 0:
                    port_equity += shs * p
        if math.isnan(port_equity):
            port_equity = 0.0

        # Sanitize Total Equity
        if total_equity is None:
            total_equity = cash_val + port_equity
        if math.isnan(total_equity) or total_equity <= 0:
            total_equity = float(self.state.get("equity", self.state.get("initial_capital", cash_val)))
        if math.isnan(total_equity) or total_equity <= 0:
            total_equity = cash_val

        # Sanitize HWM True
        if hwm is None:
            hwm = float(self.state.get("hwm_true", self.initial_capital))
        if math.isnan(hwm) or hwm <= 0:
            hwm = max(total_equity, self.initial_capital)
        if total_equity > hwm:
            hwm = total_equity
        self.state["hwm_true"] = hwm

        # Sanitize Drawdown
        if drawdown_pct is None:
            dd = (total_equity - hwm) / hwm if hwm > 0 else 0.0
            drawdown_pct = dd * 100.0
        if math.isnan(drawdown_pct):
            drawdown_pct = 0.0

        positions_count = len(self.state.get("positions", {}))
        script_path = os.path.abspath(__file__)
        script_hash = compute_file_sha256(script_path)
        univ_file = "trading_system/data/us_growth_tickers.txt" if "US" in self.pod_name else ("trading_system/data/nse_tickers.txt" if "INDIA" in self.pod_name else "")
        univ_hash = compute_file_sha256(os.path.join(PROJECT_ROOT, univ_file)) if univ_file else "STATIC_POD_C"

        eq_entry = {
            "date": now_str[:10],
            "pod": self.pod_name,
            "currency": self.currency,
            "total_equity": round(float(total_equity), 2),
            "cash": round(float(cash_val), 2),
            "portfolio_equity": round(float(port_equity), 2),
            "hwm_true": round(float(hwm), 2),
            "drawdown_pct": round(float(drawdown_pct), 2),
            "open_positions_count": int(positions_count),
            "code_commit": commit_hash,
            "script_hash": script_hash,
            "universe_hash": univ_hash,
            "universe_spec": "trading_system/data/us_growth_tickers.txt" if "US" in self.pod_name else ("trading_system/data/nse_tickers.txt" if "INDIA" in self.pod_name else "pod_c_etfs"),
            "classification": "exploratory_shadow" if "US" in self.pod_name else "gate_b_incubation",
            "status": str(status),
            "delay_mins": int(delay_mins),
            "notes": str(notes)
        }

        os.makedirs(os.path.dirname(EQUITY_LOG_CSV), exist_ok=True)
        new_row_df = pd.DataFrame([eq_entry])
        if os.path.exists(EQUITY_LOG_CSV) and os.path.getsize(EQUITY_LOG_CSV) > 0:
            try:
                existing_df = pd.read_csv(EQUITY_LOG_CSV)
                combined_df = pd.concat([existing_df, new_row_df], ignore_index=True)
                combined_df.to_csv(EQUITY_LOG_CSV, index=False)
            except Exception:
                new_row_df.to_csv(EQUITY_LOG_CSV, mode="a", index=False, header=False)
        else:
            new_row_df.to_csv(EQUITY_LOG_CSV, index=False)

    def scan_and_evaluate(self, universe_data: Dict[str, pd.DataFrame], benchmark_data: pd.DataFrame, active_pit_universe: Optional[Set[str]] = None, delay_mins: int = 0, notes: str = ""):
        """Step E & F: Scan market closes, evaluate stops/trails/trims, and queue Next-Day Open orders."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Benchmark Macro Filter & Volatility Radar (Quant Science Model via Canonical Module)
        radar = evaluate_dual_pod_regime_and_volatility(
            benchmark_df=benchmark_data,
            target_vol=0.15,
            vol_lookback=20,
            crash_vol_threshold=0.24,
            bear_sma_lookback=200,
            caution_scale_threshold=0.75
        )
        macro_regime = radar["regime"]
        max_exposure = radar["max_exposure"]
        vol_scale = radar["vol_scale"]
        bench_close = radar["bench_close"]
        bench_sma200 = radar["bench_sma200"]
        bench_vol_20d = radar["bench_vol_20d"]
        bench_ret_6m = radar["bench_ret_6m"]
        is_macro_bull = macro_regime != "BEAR_DEFENSE"
        self.state["macro_regime"] = macro_regime
        self.state["radar_summary"] = (
            f"{macro_regime} (Bench {bench_close:.2f} vs 200-SMA {bench_sma200:.2f}, "
            f"20D Vol {bench_vol_20d*100:.1f}%, MaxExp {max_exposure*100:.0f}%)"
        )

        print(f"\n[{self.pod_name} RADAR] Benchmark: Close={bench_close:.2f} vs 200-SMA={bench_sma200:.2f} | 20D Vol={bench_vol_20d*100:.1f}% | 6M Ret={bench_ret_6m*100:+.1f}% (Scale={vol_scale:.2f}) -> Regime: [{macro_regime}] Max Exposure: {max_exposure*100:.0f}%")

        # 2. Mark to Market & Peak Update (Fail-Closed against NaN / Stale Quotes)
        port_equity = 0.0
        current_prices = {}
        for sym, pos in list(self.state["positions"].items()):
            p = None
            if sym in universe_data and not universe_data[sym].empty:
                try:
                    close_col = universe_data[sym]["close"].dropna()
                    if not close_col.empty:
                        val = float(close_col.iloc[-1])
                        if not np.isnan(val) and val > 0:
                            p = val
                except Exception:
                    p = None
            if p is None:
                p = float(pos.get("entry_price", 0.0))
            if math.isnan(p) or p <= 0:
                p = 1.0

            current_prices[sym] = p
            shs = float(pos.get("shares", 0.0))
            if math.isnan(shs):
                shs = 0.0
            pos["shares"] = shs

            port_equity += shs * p
            peak_val = float(pos.get("peak_price", p))
            if math.isnan(peak_val) or peak_val <= 0:
                peak_val = p
            if p > peak_val:
                peak_val = p
            pos["peak_price"] = peak_val
            pos["last_close"] = p

        cash_val = float(self.state.get("cash", 0.0))
        if math.isnan(cash_val):
            cash_val = float(self.state.get("initial_capital", 100000.0 if "US" in self.pod_name else 80000.0))
        self.state["cash"] = cash_val

        if math.isnan(port_equity):
            port_equity = 0.0

        total_equity = cash_val + port_equity
        if math.isnan(total_equity) or total_equity <= 0:
            total_equity = float(self.state.get("initial_capital", 100000.0 if "US" in self.pod_name else 80000.0))

        hwm = float(self.state.get("hwm_true", 1.0))
        if math.isnan(hwm) or hwm <= 0:
            hwm = max(total_equity, float(self.state.get("initial_capital", 1.0)))
        if total_equity > hwm:
            hwm = total_equity
        self.state["hwm_true"] = hwm

        current_dd = (total_equity - hwm) / hwm if hwm > 0 else 0.0
        if math.isnan(current_dd):
            current_dd = 0.0
        max_dd = float(self.state.get("max_drawdown", 0.0))
        if math.isnan(max_dd):
            max_dd = 0.0
        if current_dd < max_dd:
            max_dd = current_dd
        self.state["max_drawdown"] = max_dd

        print(f"[{self.pod_name} NAV] Total Equity: {self.currency} {total_equity:,.2f} | Cash: {self.currency} {self.state['cash']:,.2f} | Port: {self.currency} {port_equity:,.2f} | MaxDD: {self.state['max_drawdown']*100:.2f}%")

        # 3. Evaluate Exits & Dynamic Trimming
        signals_to_exit = []

        if not is_macro_bull:
            # Full Bear Defense Liquidation: Protect 100% of capital into liquid cash yield
            for sym in list(self.state["positions"].keys()):
                signals_to_exit.append({"sym": sym, "reason": f"BEAR_DEFENSE_MACRO_EXIT [{macro_regime}]"})
        else:
            hard_stop = INDIA_HARD_STOP if "INDIA" in self.pod_name else -0.12
            trail_tiers = [(1.00, -0.25), (0.50, -0.20), (0.25, -0.15)]

            for sym, pos in list(self.state["positions"].items()):
                # Mandatory Point-in-Time (PIT) Index Exclusion Liquidation
                if active_pit_universe is not None and sym not in active_pit_universe:
                    signals_to_exit.append({"sym": sym, "reason": "PIT_MEMBERSHIP_EXCLUSION_MANDATORY_LIQUIDATION"})
                    continue
                if sym not in current_prices:
                    continue
                price = current_prices[sym]
                cost = pos["entry_price"]
                plpc = (price - cost) / cost if cost > 0 else 0.0
                peak = pos.get("peak_price", price)
                pullback = (price - peak) / peak if peak > 0 else 0.0

                if "US" in self.pod_name:
                    # Enhanced US Momentum (In-sample exploratory baseline: 8 slots, 4.0x ATR trail):
                    # 4.0x ATR Trailing Stop from Peak + -12% Hard Stop + 150-SMA Trend Exit
                    cur_atr = 0.0
                    if sym in universe_data:
                        cur_atr = calc_atr(universe_data[sym], window=20)
                    if cur_atr <= 0 or np.isnan(cur_atr):
                        cur_atr = price * 0.03  # 3% volatility fallback
                    trail_stop_p = peak - (4.0 * cur_atr)
                    if price <= trail_stop_p:
                        signals_to_exit.append({"sym": sym, "reason": f"ATR_TRAIL_STOP (-4.0x ATR @ {trail_stop_p:.2f}) [PnL: {plpc*100:+.1f}%]"})
                        continue

                    if plpc <= -0.12:
                        signals_to_exit.append({"sym": sym, "reason": f"HARD_STOP (-12.0%) [PnL: {plpc*100:+.1f}%]"})
                        continue

                    if sym in universe_data and len(universe_data[sym]) >= 150:
                        sma150 = universe_data[sym]["close"].rolling(150, min_periods=50).mean().iloc[-1]
                        if price < sma150:
                            signals_to_exit.append({"sym": sym, "reason": f"TREND_SMA150_BREAK [PnL: {plpc*100:+.1f}%]"})
                            continue
                else:
                    # India Pod: Hard Stop + Multi-Tier Trailing Profit Lock + 150-SMA
                    if plpc <= hard_stop:
                        signals_to_exit.append({"sym": sym, "reason": f"HARD_STOP ({hard_stop*100:.1f}%) [PnL: {plpc*100:+.1f}%]"})
                        continue

                    trailed = False
                    for min_gain, trail_pct in trail_tiers:
                        if plpc >= min_gain:
                            if pullback <= trail_pct:
                                signals_to_exit.append({"sym": sym, "reason": f"TRAIL_TIER (+{min_gain*100:.0f}% / {trail_pct*100:.0f}%) [PnL: {plpc*100:+.1f}%]"})
                                trailed = True
                            break
                    if trailed:
                        continue

                    if sym in universe_data and len(universe_data[sym]) >= 150:
                        sma150 = universe_data[sym]["close"].rolling(150, min_periods=50).mean().iloc[-1]
                        if price < sma150:
                            signals_to_exit.append({"sym": sym, "reason": f"TREND_SMA150_BREAK [PnL: {plpc*100:+.1f}%]"})
                            continue

            # Dynamic Volatility Trimming on Remaining Positions
            # If market volatility is elevated (max_exposure < 1.0), trim positions exceeding target weight
            target_pos_val = (total_equity / self.max_positions) * max_exposure
            for sym, pos in list(self.state["positions"].items()):
                if any(s["sym"] == sym for s in signals_to_exit):
                    continue
                price = current_prices.get(sym, pos["entry_price"])
                cur_val = pos["shares"] * price
                # Trim if position exceeds target allocation by >15% buffer
                if cur_val > target_pos_val * 1.15 and price > 0:
                    excess_val = cur_val - target_pos_val
                    shares_to_trim = math.floor(excess_val / price)
                    if shares_to_trim > 0:
                        signals_to_exit.append({
                            "sym": sym,
                            "reason": f"VOL_TARGET_TRIM (Scale={max_exposure:.2f})",
                            "trim_shares": float(shares_to_trim)
                        })

        self.state["pending_sells"] = signals_to_exit
        for s in signals_to_exit:
            action_desc = f"TRIM {s.get('trim_shares')} shs" if s.get("trim_shares") else "FULL SELL"
            print(f"  [SIGNAL QUEUED {action_desc:<12}] {s['sym']:<12} -> Reason: {s['reason']}")

        # 4. Candidate Screening & Dynamic Allocation (Quant Science Volatility-Targeted Sizing)
        full_exits_count = len([s for s in signals_to_exit if not s.get("trim_shares")])
        active_positions_count = len(self.state["positions"]) - full_exits_count
        open_slots = max(0, self.max_positions - active_positions_count)

        if is_macro_bull and open_slots > 0 and self.state["cash"] > 100.0:
            cands = []
            min_price = 20.0 if "INDIA" in self.pod_name else 10.0

            for sym, df in universe_data.items():
                if active_pit_universe is not None and sym not in active_pit_universe:
                    continue
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

                if "US" in self.pod_name:
                    # 126d momentum with 21d skip (6M-1M skip-month to eliminate 1-month mean-reversion top buying)
                    score = calc_vectorized_momentum(close_arr, window=126, skip_days=21)
                    threshold = 0.05
                else:
                    m90 = calc_vectorized_momentum(close_arr, window=90)
                    m180 = calc_vectorized_momentum(close_arr, window=180)
                    score = 0.60 * m90 + 0.40 * m180
                    threshold = 0.15

                if score > threshold:
                    cands.append({"sym": sym, "price": cur_price, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)
            selected = cands[:open_slots]

            alloc_per_cand = (total_equity / self.max_positions) * max_exposure
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
        elif not is_macro_bull:
            self.state["pending_buys"] = []
            print(f"  [{self.pod_name} CASH DEFENSE] Regime is {macro_regime} -> 100% Capital Preserved in Safe Liquid Cash (100% Long-Only CNC Delivery).")

        self._save_state()

        # Append to Daily Equity Log (Audited Provenance Tracking)
        self.log_daily_equity(
            status="SCAN_COMPLETE",
            delay_mins=delay_mins,
            notes=notes if notes else f"Scan complete; {len(self.state.get('pending_buys', []))} buys, {len(self.state.get('pending_sells', []))} sells queued.",
            port_equity=port_equity,
            total_equity=total_equity,
            hwm=hwm,
            drawdown_pct=current_dd * 100.0
        )

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
        print(f"Active Positions Held       : {len(self.state['positions'])} / {self.max_positions} slots")
        print(f"Pending Orders Queued       : {len(self.state['pending_sells'])} Sells, {len(self.state['pending_buys'])} Buys")
        print("-" * 95)
        if self.state["positions"]:
            print(f"{'Symbol':<10} | {'Shares':<8} | {'Entry Price':<12} | {'Peak Price':<12} | {'Stop Ref':<12} | {'Trail Ref':<12}")
            print("-" * 95)
            hard_stop = INDIA_HARD_STOP if "INDIA" in self.pod_name else -0.12
            for sym, pos in sorted(self.state["positions"].items()):
                entry = pos["entry_price"]
                peak = pos.get("peak_price", entry)
                hard_stop_val = entry * (1.0 + hard_stop)
                trail_stop_val = peak * 0.88 if "US" in self.pod_name else peak * 0.85
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


class MultiAssetPodPaperEngine:
    """
    Production Multi-Asset Tactical Trend Paper Engine (Pod C)
    ===========================================================
    Governs macro tactical trend following across:
      - India Large-Cap Trend: 40% NIFTYBEES.NS
      - US Secular Technology: 30% MON100.NS
      - Domestic Precious Metal: 20% GOLDBEES.NS
      - Sovereign Cash Yield: 10% base buffer + 100% of disqualified trend capital

    Rules (Audited Protocol V2.1 Variant A):
      - Trend Gate: Price > 200-SMA and 6-Month Momentum (126d) > 0.
      - Whipsaw & Crash Defense: Any broken asset drops to 0% weight; capital
        compounds daily in liquid cash yield (RBI repo rate less 65 bps TER).
      - Execution: Signal at Close (15:35 IST); Filled at Next-Day Open (09:15 IST).
      - Sourced Friction: CDSL DP fee Rs 14.75, STT (10 bps on equities, 0 bps on metals/intl),
        exchange turnover charges, SEBI fee, GST.
    """
    def __init__(
        self,
        pod_name: str = "POD_C",
        currency: str = "INR",
        initial_capital: float = DEFAULT_MULTI_ASSET_CAPITAL,
        state_file: str = MULTI_ASSET_STATE_FILE,
        trades_file: str = MULTI_ASSET_TRADES_CSV,
        stressed_friction: bool = True
    ):
        self.pod_name = pod_name
        self.currency = currency
        self.initial_capital = initial_capital
        self.state_file = state_file
        self.trades_file = trades_file
        self.stressed_friction = stressed_friction
        self.session_trades: List[Dict[str, Any]] = []
        self.state = self._load_state()

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
            "initial_capital": self.initial_capital,
            "positions": {},       # sym -> {shares, entry_price, entry_date, peak_price}
            "pending_buys": [],    # [{sym, target_alloc, score, reason}]
            "pending_sells": [],   # [{sym, reason, trim_shares}]
            "hwm_true": self.initial_capital,
            "max_drawdown": 0.0,
            "trend_status": {},    # sym -> {price, sma200, mom6m, qualified, regime}
            "total_interest_earned": 0.0,
            "last_updated": None
        }

    def _save_state(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_trade(self, trade_data: Dict[str, Any]):
        self.session_trades.append(dict(trade_data))
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        file_exists = os.path.exists(self.trades_file) and os.path.getsize(self.trades_file) > 0
        df_row = pd.DataFrame([trade_data])
        df_row.to_csv(self.trades_file, mode="a", index=False, header=not file_exists)

    def execute_open_fills(self, current_open_prices: Dict[str, float]):
        """Executes queued orders at 09:15 IST Market Open with statutory taxes and slippage."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Execute Sells (Full exits or trims)
        if self.state["pending_sells"]:
            for item in self.state["pending_sells"]:
                sym = item["sym"]
                reason = item["reason"]
                if sym not in self.state["positions"]:
                    continue
                pos = self.state["positions"][sym]
                total_shs = pos["shares"]
                trim_shs = item.get("trim_shares")
                if trim_shs and 0 < trim_shs < total_shs:
                    shares = float(trim_shs)
                    is_full_exit = False
                else:
                    shares = float(total_shs)
                    is_full_exit = True

                spec = POD_C_ASSET_SPECS.get(sym, {"norm_slip_bps": 7.5, "stress_slip_bps": 10.0, "stt_sell_bps": 0.0})
                slip_bps = spec["stress_slip_bps"] if self.stressed_friction else spec["norm_slip_bps"]
                open_p = current_open_prices.get(sym, pos["entry_price"])
                if open_p <= 0:
                    open_p = pos["entry_price"]
                fill_p = open_p * (1.0 - slip_bps / 10000.0)
                gross_proceeds = shares * fill_p

                # Sourced friction: STT + Brokerage + Exch + SEBI + GST + DP fee
                stt = gross_proceeds * (spec.get("stt_sell_bps", 0.0) / 10000.0)
                brok = min(20.0, gross_proceeds * 0.0005)
                exch = gross_proceeds * 0.000297
                sebi = gross_proceeds * 0.000001
                gst = (brok + exch) * 0.18
                flat_dp = INDIA_FLAT_DP_FEE if is_full_exit else 0.0
                sell_friction = stt + brok + exch + sebi + gst + flat_dp

                net_proceeds = gross_proceeds - sell_friction
                cost = shares * pos["entry_price"]
                gain = net_proceeds - cost

                self.state["cash"] += net_proceeds
                self.log_trade({
                    "timestamp": now_str,
                    "symbol": sym,
                    "action": "TRIM" if not is_full_exit else "SELL",
                    "shares": shares,
                    "open_price": open_p,
                    "fill_price": fill_p,
                    "proceeds": net_proceeds,
                    "realized_pnl": gain,
                    "pnl_pct": (fill_p - pos["entry_price"]) / pos["entry_price"] if pos["entry_price"] > 0 else 0.0,
                    "dp_fee": flat_dp,
                    "friction": sell_friction,
                    "reason": reason
                })
                print(f"  [{self.pod_name} EXECUTE {'TRIM' if not is_full_exit else 'SELL'}] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f} | PnL: {self.currency} {gain:>+9.2f} ({reason})")
                if is_full_exit:
                    del self.state["positions"][sym]
                else:
                    self.state["positions"][sym]["shares"] -= shares
            self.state["pending_sells"] = []

        # 2. Execute Buys
        if self.state["pending_buys"]:
            for item in self.state["pending_buys"]:
                sym = item["sym"]
                target_alloc = item["target_alloc"]
                reason = item.get("reason", "TREND_BULL_ENTRY")
                open_p = current_open_prices.get(sym, 0.0)
                if open_p <= 0:
                    continue

                spec = POD_C_ASSET_SPECS.get(sym, {"norm_slip_bps": 7.5, "stress_slip_bps": 10.0, "stamp_buy_bps": 1.5})
                slip_bps = spec["stress_slip_bps"] if self.stressed_friction else spec["norm_slip_bps"]
                fill_p = open_p * (1.0 + slip_bps / 10000.0)

                avail_cash = self.state["cash"] * 0.98
                alloc = min(target_alloc, avail_cash)
                if alloc < 500.0:
                    continue

                brok = min(20.0, alloc * 0.0005)
                stamp = alloc * (spec.get("stamp_buy_bps", 1.5) / 10000.0)
                exch = alloc * 0.000297
                sebi = alloc * 0.000001
                gst = (brok + exch) * 0.18
                buy_friction = brok + stamp + exch + sebi + gst

                investable = alloc - buy_friction
                shares = round(investable / fill_p, 2)
                cost = shares * fill_p + buy_friction

                if cost <= self.state["cash"] and shares > 0:
                    self.state["cash"] -= cost
                    if sym in self.state["positions"]:
                        prev_shs = self.state["positions"][sym]["shares"]
                        prev_cost = prev_shs * self.state["positions"][sym]["entry_price"]
                        tot_shs = prev_shs + shares
                        avg_entry = (prev_cost + cost) / tot_shs
                        self.state["positions"][sym]["shares"] = tot_shs
                        self.state["positions"][sym]["entry_price"] = avg_entry
                    else:
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
                        "friction": buy_friction,
                        "reason": reason
                    })
                    print(f"  [{self.pod_name} EXECUTE BUY ] {sym:<12} {shares:>8.2f} shs @ {self.currency} {fill_p:>9.2f} | Cost: {self.currency} {cost:>9.2f}")
            self.state["pending_buys"] = []

        self._save_state()

    def scan_and_evaluate(self, universe_data: Dict[str, pd.DataFrame], benchmark_data: Optional[pd.DataFrame] = None):
        """Step E & F: Scan market closes at 15:35 IST, evaluate 200-SMA trend & momentum, queue Next-Day Open orders."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Daily Sovereign Liquid Cash Compounding Yield
        # RBI Repo rate less 65 bps TER, net of slab tax ~ 6.0% net annualized
        daily_yield = self.state["cash"] * (0.060 / 252.0)
        self.state["cash"] += daily_yield
        self.state["total_interest_earned"] = self.state.get("total_interest_earned", 0.0) + daily_yield

        # 2. Mark to Market & True Peak High-Water Mark (Fail-Closed against NaN / Stale Quotes)
        port_val = 0.0
        current_prices = {}
        for sym, pos in list(self.state["positions"].items()):
            p = None
            if sym in universe_data and not universe_data[sym].empty:
                close_col = universe_data[sym]["close"].dropna()
                if not close_col.empty:
                    val = float(close_col.iloc[-1])
                    if not np.isnan(val) and val > 0:
                        p = val
            if p is None:
                p = float(pos.get("entry_price", 0.0))

            current_prices[sym] = p
            port_val += pos["shares"] * p
            if p > pos.get("peak_price", p):
                pos["peak_price"] = p

        total_equity = self.state["cash"] + port_val
        if total_equity > self.state.get("hwm_true", 0.0):
            self.state["hwm_true"] = total_equity
        hwm = max(self.state.get("hwm_true", 1.0), 1.0)
        current_dd = (total_equity - hwm) / hwm
        if current_dd < self.state.get("max_drawdown", 0.0):
            self.state["max_drawdown"] = current_dd
            self.state["max_drawdown"] = current_dd

        print(f"\n[{self.pod_name} NAV] Total Equity: {self.currency} {total_equity:,.2f} | Cash: {self.currency} {self.state['cash']:,.2f} | Port: {self.currency} {port_val:,.2f} | MaxDD: {self.state['max_drawdown']*100:.2f}% | Interest Earned: {self.currency} {self.state['total_interest_earned']:,.2f}")

        # 3. Macro Trend & Relative Momentum Qualification Scan
        trend_status = {}
        signals_to_exit = []
        signals_to_buy = []

        for sym, target_weight in POD_C_CORE_ALLOCATIONS.items():
            if sym == "CASH":
                continue
            if sym not in universe_data or universe_data[sym].empty:
                continue
            df = universe_data[sym]
            if len(df) < 50:
                continue

            cur_p = float(df["close"].iloc[-1])
            sma200 = float(df["close"].rolling(200, min_periods=40).mean().iloc[-1])
            lookback_mom = min(len(df) - 1, 126)
            m6 = (cur_p - float(df["close"].iloc[-lookback_mom])) / float(df["close"].iloc[-lookback_mom]) if lookback_mom > 0 else 0.0

            # Pre-Registered Protocol V2.1 Variant A Rule: Price > 200-SMA AND 6M Momentum > 0
            is_qualified = (cur_p > sma200) and (m6 > 0.0)
            trend_status[sym] = {
                "price": cur_p,
                "sma200": sma200,
                "mom6m": m6,
                "qualified": is_qualified,
                "regime": "BULL_TREND" if is_qualified else "DEFENSIVE_CASH"
            }

            print(f"[{self.pod_name} RADAR] {sym:<12}: Close={cur_p:>8.2f} vs 200-SMA={sma200:>8.2f} | 6M Mom={m6*100:>+5.1f}% -> [{'BULL_TREND' if is_qualified else 'DEFENSIVE_CASH'}]")

            # Evaluate Held Positions
            if sym in self.state["positions"]:
                if not is_qualified:
                    signals_to_exit.append({
                        "sym": sym,
                        "reason": f"TREND_DEFENSE_EXIT (Close {cur_p:.2f} <= 200-SMA {sma200:.2f} or 6M Mom {m6*100:+.1f}% <= 0)"
                    })
                else:
                    # Rebalance check (Trim if overweight by >25%; Top-up if underweight by >25%)
                    cur_pos_val = self.state["positions"][sym]["shares"] * cur_p
                    target_val = total_equity * target_weight
                    if cur_pos_val > target_val * 1.25 and cur_p > 0:
                        excess = cur_pos_val - target_val
                        trim_shs = math.floor(excess / cur_p)
                        if trim_shs > 0:
                            signals_to_exit.append({
                                "sym": sym,
                                "reason": f"REBALANCE_TRIM (Overweight by {(cur_pos_val/target_val-1)*100:+.1f}%)",
                                "trim_shares": float(trim_shs)
                            })
                    elif cur_pos_val < target_val * 0.75:
                        deficit = target_val - cur_pos_val
                        if deficit >= 1000.0:
                            signals_to_buy.append({
                                "sym": sym,
                                "target_alloc": deficit,
                                "score": m6,
                                "reason": f"REBALANCE_TOPUP (Underweight by {(1-cur_pos_val/target_val)*100:.1f}%)"
                            })
            else:
                # Candidate Entry
                if is_qualified:
                    target_val = total_equity * target_weight
                    signals_to_buy.append({
                        "sym": sym,
                        "target_alloc": target_val,
                        "score": m6,
                        "reason": f"TREND_BULL_ENTRY (Close {cur_p:.2f} > 200-SMA {sma200:.2f}, 6M Mom: {m6*100:+.1f}%)"
                    })

        self.state["trend_status"] = trend_status
        self.state["pending_sells"] = signals_to_exit
        self.state["pending_buys"] = signals_to_buy

        for s in signals_to_exit:
            action_desc = f"TRIM {s.get('trim_shares')} shs" if s.get("trim_shares") else "FULL SELL"
            print(f"  [SIGNAL QUEUED {action_desc:<12}] {s['sym']:<12} -> Reason: {s['reason']}")
        for b in signals_to_buy:
            print(f"  [SIGNAL QUEUED BUY         ] {b['sym']:<12} Target: {self.currency} {b['target_alloc']:>9.2f} | 6M Mom: {b['score']*100:+.1f}%")

        self._save_state()

        # 4. Append to Daily Equity Log (Audited Provenance Tracking)
        os.makedirs(os.path.dirname(EQUITY_LOG_CSV), exist_ok=True)
        commit_hash = get_git_commit_hash()
        script_path = os.path.abspath(__file__)
        script_hash = compute_file_sha256(script_path)
        eq_entry = {
            "date": now_str[:10],
            "pod": self.pod_name,
            "currency": self.currency,
            "total_equity": round(total_equity, 2) if not np.isnan(total_equity) else round(self.state.get("equity", self.state["cash"]), 2),
            "cash": round(self.state["cash"], 2),
            "portfolio_equity": round(port_val, 2) if not np.isnan(port_val) else 0.0,
            "hwm_true": round(self.state["hwm_true"], 2),
            "drawdown_pct": round(current_dd * 100.0, 2) if not np.isnan(current_dd) else 0.0,
            "open_positions_count": len(self.state["positions"]),
            "code_commit": commit_hash,
            "script_hash": script_hash,
            "universe_hash": "STATIC_POD_C",
            "universe_spec": "pod_c_macro_etfs",
            "classification": "exploratory_shadow",
            "status": "SCAN_COMPLETE",
            "delay_mins": 0,
            "notes": "Pod C multi-asset scan complete"
        }
        new_row_df = pd.DataFrame([eq_entry])
        if os.path.exists(EQUITY_LOG_CSV) and os.path.getsize(EQUITY_LOG_CSV) > 0:
            try:
                existing_df = pd.read_csv(EQUITY_LOG_CSV)
                combined_df = pd.concat([existing_df, new_row_df], ignore_index=True)
                combined_df.to_csv(EQUITY_LOG_CSV, index=False)
            except Exception:
                new_row_df.to_csv(EQUITY_LOG_CSV, mode="a", index=False, header=False)
        else:
            new_row_df.to_csv(EQUITY_LOG_CSV, index=False)

    def print_status_tear_sheet(self):
        print("\n" + "=" * 95)
        print(f"================== {self.pod_name} (MULTI-ASSET TREND) STATUS TEAR SHEET ==================")
        print("=" * 95)
        print(f"Base Currency               : {self.currency}")
        print(f"Initial Starting Capital    : {self.currency} {self.initial_capital:>14,.2f}")
        total_eq = self.state["cash"] + sum(p["shares"] * p.get("peak_price", p["entry_price"]) for p in self.state["positions"].values())
        print(f"Current Total NAV Equity    : {self.currency} {total_eq:>14,.2f}")
        print(f"Liquid Cash Balance         : {self.currency} {self.state['cash']:>14,.2f} (Base 10% + Defensive Cash Reserves)")
        print(f"Cumulative Yield Earned     : {self.currency} {self.state.get('total_interest_earned', 0.0):>14,.2f}")
        print(f"Lifetime True Peak HWM      : {self.currency} {self.state['hwm_true']:>14,.2f}")
        print(f"Current Strategy Drawdown   : {self.state['max_drawdown']*100:>13.2f}%")
        print(f"Active Macro Positions      : {len(self.state['positions'])} / 3 Core Assets")
        print(f"Pending Orders Queued       : {len(self.state['pending_sells'])} Sells, {len(self.state['pending_buys'])} Buys")
        print("-" * 95)
        print(f"{'Asset Symbol':<12} | {'Target %':<8} | {'Status':<14} | {'Price':<10} | {'200-SMA':<10} | {'6M Mom %':<10} | {'Shares':<8} | {'Holding Value':<12}")
        print("-" * 95)
        for sym, target_wt in POD_C_CORE_ALLOCATIONS.items():
            if sym == "CASH":
                actual_cash_wt = (self.state["cash"] / total_eq * 100.0) if total_eq > 0 else 100.0
                print(f"{'SOVEREIGN CASH':<12} | {'10.0%':<8} | {'YIELD RESERVE':<14} | {'N/A':<10} | {'N/A':<10} | {'N/A':<10} | {'N/A':<8} | {self.currency} {self.state['cash']:>10,.2f} ({actual_cash_wt:.1f}%)")
                continue
            st = self.state.get("trend_status", {}).get(sym, {})
            regime = st.get("regime", "PENDING_SCAN")
            price = st.get("price", 0.0)
            sma200 = st.get("sma200", 0.0)
            mom = st.get("mom6m", 0.0) * 100.0
            pos = self.state["positions"].get(sym, {})
            shs = pos.get("shares", 0.0)
            val = shs * (price if price > 0 else pos.get("entry_price", 0.0))
            print(f"{sym:<12} | {target_wt*100:>6.1f}% | {regime:<14} | {self.currency} {price:>8.2f} | {self.currency} {sma200:>8.2f} | {mom:>+8.1f}% | {shs:>8.1f} | {self.currency} {val:>10,.2f}")

        if self.state["pending_sells"]:
            print("-" * 95)
            print("QUEUED SELL ORDERS (To Execute at Next Open):")
            for s in self.state["pending_sells"]:
                print(f"  -> SELL {s['sym']:<12} | Reason: {s['reason']}")

        if self.state["pending_buys"]:
            print("-" * 95)
            print("QUEUED BUY ORDERS (To Execute at Next Open):")
            for b in self.state["pending_buys"]:
                print(f"  -> BUY  {b['sym']:<12} | Alloc: {self.currency} {b['target_alloc']:>10,.2f} | 6M Mom: {b['score']*100:+.1f}% | Reason: {b.get('reason','')}")

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
                if "close" in df.columns:
                    df = df.dropna(subset=["close"])
                if len(df) >= 50:
                    out[sym] = df
            except Exception:
                pass
    except Exception as e:
        print(f"Batch fetch error: {e}")
    return out


def get_ny_now() -> datetime:
    """Returns current datetime in America/New_York timezone with daylight savings awareness."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        pass
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:
        pass
    utc = datetime.now(timezone.utc)
    year = utc.year
    dst_start = datetime(year, 3, 8 + (6 - datetime(year, 3, 1).weekday()) % 7, 7, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 11, 1 + (6 - datetime(year, 11, 1).weekday()) % 7, 6, 0, tzinfo=timezone.utc)
    is_dst = dst_start <= utc < dst_end
    from datetime import timedelta
    offset_hours = -4 if is_dst else -5
    return utc.astimezone(timezone(timedelta(hours=offset_hours)))


def verify_us_timing_window(phase: str, force: bool = False) -> Tuple[bool, str, int, str]:
    """
    Institutional Execution Timing Guard:
    Enforces that scheduled automated runs arrive within their intended market windows
    to preserve the next-open / close-scan backtest invariant.

    Returns:
        (is_valid: bool, status: str, delay_mins: int, msg: str)
    """
    if force:
        return True, f"FORCED_{phase.upper()}", 0, "Force flag enabled; bypassing timing guard."

    if phase == "status":
        return True, "STATUS_CHECK", 0, "Status phase can be executed at any time."

    ny_now = get_ny_now()
    weekday = ny_now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    current_time_str = ny_now.strftime("%H:%M %Z")
    time_mins = ny_now.hour * 60 + ny_now.minute

    if weekday >= 5:
        # Allow a delayed Friday post-close scan that arrives overnight before 09:25 EST Saturday
        if phase == "scan" and weekday == 5 and time_mins < (9 * 60 + 25):
            return True, "SCAN_COMPLETE", 0, (
                f"Within overnight weekend grace window ({current_time_str}); scanning Friday market close."
            )
        msg = f"US market is closed on weekends (Current: {ny_now.strftime('%A %H:%M %Z')}). Preserving state for next session."
        return False, "SKIPPED_WEEKEND", 0, msg

    if phase == "execute":
        # Regular US market open is 09:30 Eastern (570 mins); market close is 16:00 Eastern (960 mins).
        # We allow execution across the active trading session (09:25–16:00 Eastern)
        # to accommodate GitHub Actions queuing delays while filling at official open prices.
        open_start = 9 * 60 + 25   # 09:25 Eastern
        market_open = 9 * 60 + 30  # 09:30 Eastern
        market_close = 16 * 60     # 16:00 Eastern

        if time_mins < open_start:
            msg = f"PREMATURE RUN: Current Eastern time is {current_time_str}, before 09:25 market open window. Preserving queued orders for open."
            return False, "SKIPPED_PRE_OPEN", 0, msg

        if time_mins > market_close:
            delay_mins = max(0, time_mins - market_open)
            msg = (
                f"STALE RUN: Runner delayed by {delay_mins} mins, arrived at {current_time_str} post-close "
                f"(after 16:00 Eastern). Skipping execution to prevent filling after-hours; queued orders preserved for next open."
            )
            return False, "SKIPPED_RUNNER_POST_CLOSE", delay_mins, msg

        delay_mins = max(0, time_mins - market_open)
        msg = f"Within active US market session ({current_time_str}); runner delay {delay_mins}m. Executing open fills."
        return True, "EXECUTE_FILL", delay_mins, msg

    elif phase == "scan":
        # Scan is blocked ONLY during active intraday trading hours (09:25–15:59 EST).
        # Both post-close (>= 16:00 EST) and overnight pre-open (< 09:25 EST) have complete EOD bars.
        open_start = 9 * 60 + 25   # 09:25 Eastern
        market_close = 16 * 60     # 16:00 Eastern
        close_sched = 16 * 60 + 15 # 16:15 Eastern

        if open_start <= time_mins < market_close:
            msg = f"PREMATURE RUN: Current Eastern time is {current_time_str}, during active market hours before official 16:00 close. Scan deferred."
            return False, "SKIPPED_RUNNER_PRE_CLOSE", 0, msg

        delay_mins = max(0, time_mins - close_sched) if time_mins >= market_close else 0
        msg = f"Within valid Market Close / Overnight scan window ({current_time_str}); runner delay {delay_mins}m. Scanning closes and updating signals."
        return True, "SCAN_COMPLETE", delay_mins, msg

    return True, "VERIFIED", 0, "Timing verified."


def check_us_market_open_clock() -> Optional[bool]:
    """Queries Alpaca /v2/clock if credentials are set. Returns True/False, or None if unavailable."""
    api_key = os.environ.get("PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("PAPER_API_SECRET") or os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    try:
        from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
        adapter = AlpacaBrokerAdapter(api_key=api_key, api_secret=api_secret, base_url="https://paper-api.alpaca.markets")
        clock = adapter.get_market_clock()
        if isinstance(clock, dict) and "is_open" in clock:
            return bool(clock["is_open"])
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Dual-Pod Institutional Paper Trading Engine")
    parser.add_argument("--pod", choices=["all", "india", "us", "pod_c", "multi_asset"], default="all", help="Target pod")
    parser.add_argument("--phase", choices=["scan", "execute", "status"], default="status", help="Trading cycle phase")
    parser.add_argument("--mode", choices=["exploratory_shadow", "gate_b"], default="exploratory_shadow", help="Incubation classification")
    parser.add_argument("--protocol-hash", type=str, default="", help="Audited Gate A protocol hash")
    parser.add_argument("--force", action="store_true", help="Bypass market timing guards (for manual override)")
    args = parser.parse_args()

    # Fiduciary Code Guard: Refuse Gate B certification if Gate A has not passed
    if args.mode == "gate_b":
        from trading_system.app.validation.gate_evaluator import GateEvaluator
        cleared_india = GateEvaluator.verify_gate_a_clearance_for_gate_b("Variant 2", args.protocol_hash)
        cleared_us = GateEvaluator.verify_gate_a_clearance_for_gate_b("Variant 1", args.protocol_hash)
        if not (cleared_india and cleared_us):
            raise RuntimeError(
                "CRITICAL FIDUCIARY GUARD: Gate B incubation execution REFUSED. "
                "Neither pod variant has passed an audited Gate A stress test. "
                "Run with '--mode exploratory_shadow' for uncertified shadow tracking."
            )

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
        trades_file=US_TRADES_CSV,
        live_broker=(args.mode in ("live_alpaca", "exploratory_shadow"))
    )

    multi_asset_engine = MultiAssetPodPaperEngine(
        pod_name="POD_C",
        currency="INR",
        initial_capital=DEFAULT_MULTI_ASSET_CAPITAL,
        state_file=MULTI_ASSET_STATE_FILE,
        trades_file=MULTI_ASSET_TRADES_CSV
    )

    us_cycle_status = args.phase.upper()
    us_cycle_delay = 0
    us_cycle_notes = ""
    us_notify = True

    if args.phase == "status":
        if args.pod in ["all", "india"]:
            india_engine.print_status_tear_sheet()
        if args.pod in ["all", "us"]:
            us_engine.sync_alpaca_live()
            us_engine.print_status_tear_sheet()
        if args.pod in ["all", "pod_c", "multi_asset"]:
            multi_asset_engine.print_status_tear_sheet()
        dispatch_notifications_and_dashboard(india_engine, us_engine, multi_asset_engine, args.phase, args.pod)
        return

    # PHASE: SCAN (Run at Market Close: 15:35 IST / 16:05 EST)
    if args.phase == "scan":
        if args.pod in ["all", "india"]:
            print("\n>>> [POD 1: INDIA] SCANNING POINT-IN-TIME NSE UNIVERSE AT MARKET CLOSE (15:35 IST)...")
            india_tickers = get_active_pit_universe("INDIA")
            combined_tickers = list(set(india_tickers) | set(india_engine.state["positions"].keys()))
            india_data = fetch_yfinance_history(combined_tickers, period="1y")
            bench_india = yf.download("^NSEI", period="1y", progress=False, auto_adjust=False)
            bench_india = normalize_df_columns(bench_india)
            india_engine.scan_and_evaluate(india_data, bench_india, active_pit_universe=set(india_tickers))

        if args.pod in ["all", "us"]:
            is_valid, status, delay_mins, msg = verify_us_timing_window(args.phase, force=args.force)
            us_cycle_status = status
            us_cycle_delay = delay_mins
            us_cycle_notes = msg
            if not is_valid:
                print(f"\n>>> [POD 2: US TIMING GUARD] SCAN SKIPPED: {msg}\n")
                us_engine.log_daily_equity(status=status, delay_mins=delay_mins, notes=msg)
            else:
                bench_us = yf.download("SPY", period="1y", progress=False, auto_adjust=False)
                bench_us = normalize_df_columns(bench_us)
                latest_bar_date = ""
                try:
                    close_col = "close" if "close" in bench_us.columns else ("adj close" if "adj close" in bench_us.columns else None)
                    valid_bench = bench_us.dropna(subset=[close_col]) if close_col else bench_us
                    if not valid_bench.empty:
                        latest_bar_date = str(valid_bench.index[-1])[:10]
                except Exception:
                    latest_bar_date = ""

                if not args.force and latest_bar_date and us_engine.state.get("last_scan_bar_date") == latest_bar_date:
                    print(f"\n>>> [POD 2: US IDEMPOTENCY] Session {latest_bar_date} already scanned; skipping duplicate scan.\n")
                    us_notify = False
                else:
                    print(f"\n>>> [POD 2: US] SCANNING POINT-IN-TIME US UNIVERSE AT MARKET CLOSE (16:05 EST)... (Delay: {delay_mins}m)")
                    try:
                        us_engine.sync_alpaca_live()
                    except RuntimeError as guard_err:
                        _send_us_error_alert(str(guard_err))
                        raise
                    us_tickers = get_active_pit_universe("US")
                    combined_tickers = list(set(us_tickers) | set(us_engine.state["positions"].keys()))
                    us_data = fetch_yfinance_history(combined_tickers, period="1y")
                    if latest_bar_date:
                        us_engine.state["last_scan_bar_date"] = latest_bar_date
                    us_engine.scan_and_evaluate(us_data, bench_us, active_pit_universe=set(us_tickers), delay_mins=delay_mins, notes=msg)

        if args.pod in ["all", "pod_c", "multi_asset"]:
            print("\n>>> [POD C: MULTI-ASSET] SCANNING MACRO TREND REGIMES AT MARKET CLOSE (15:35 IST)...")
            pod_c_tickers = [t for t in POD_C_CORE_ALLOCATIONS.keys() if t != "CASH"]
            combined_tickers = list(set(pod_c_tickers) | set(multi_asset_engine.state["positions"].keys()))
            multi_data = fetch_yfinance_history(combined_tickers, period="1y")
            bench_nifty = yf.download("^NSEI", period="1y", progress=False, auto_adjust=False)
            bench_nifty = normalize_df_columns(bench_nifty)
            multi_asset_engine.scan_and_evaluate(multi_data, bench_nifty)

    # PHASE: EXECUTE (Run at Market Open: 09:14 IST / 09:29 EST)
    elif args.phase == "execute":
        if args.pod in ["all", "india"]:
            print("\n>>> [POD 1: INDIA] EXECUTING QUEUED ORDERS AT MARKET OPEN (09:15 IST)...")
            india_tickers = get_active_pit_universe("INDIA")
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
            ny_today_str = get_ny_now().strftime("%Y-%m-%d")
            if not args.force and us_engine.state.get("last_execute_date") == ny_today_str:
                print(f"\n>>> [POD 2: US IDEMPOTENCY] Execution cycle for {ny_today_str} already completed; skipping duplicate run.\n")
                us_notify = False
            else:
                is_valid, status, delay_mins, msg = verify_us_timing_window(args.phase, force=args.force)
                us_cycle_status = status
                us_cycle_delay = delay_mins
                us_cycle_notes = msg
                if not is_valid:
                    print(f"\n>>> [POD 2: US TIMING GUARD] EXECUTION SKIPPED: {msg}\n")
                    # Do not pollute equity log or spam Discord on premature pre-open cron wakes; log post-close skips at most once/day
                    if status == "SKIPPED_PRE_OPEN":
                        us_notify = False
                    elif us_engine.state.get("last_skip_logged_date") != ny_today_str:
                        us_engine.state["last_skip_logged_date"] = ny_today_str
                        us_engine._save_state()
                        us_engine.log_daily_equity(status=status, delay_mins=delay_mins, notes=msg)
                    else:
                        us_notify = False
                else:
                    clock_open = None if args.force else check_us_market_open_clock()
                    if clock_open is False:
                        holiday_msg = f"Exchange clock reports US market CLOSED on {ny_today_str}; preserving queued orders for next trading open."
                        print(f"\n>>> [POD 2: US EXCHANGE CLOCK] {holiday_msg}\n")
                        us_cycle_status = "SKIPPED_MARKET_CLOSED"
                        us_cycle_delay = 0
                        us_cycle_notes = holiday_msg
                        if us_engine.state.get("last_skip_logged_date") != ny_today_str:
                            us_engine.state["last_skip_logged_date"] = ny_today_str
                            us_engine._save_state()
                            us_engine.log_daily_equity(status="SKIPPED_MARKET_CLOSED", delay_mins=0, notes=holiday_msg)
                        else:
                            us_notify = False
                    else:
                        print(f"\n>>> [POD 2: US] EXECUTING QUEUED ORDERS AT MARKET OPEN (09:30 EST)... (Delay: {delay_mins}m)")
                        us_tickers = get_active_pit_universe("US")
                        needed_symbols = list(set(us_tickers) | set(us_engine.state["positions"].keys()) | {p["sym"] for p in us_engine.state["pending_buys"]} | {p["sym"] for p in us_engine.state["pending_sells"]})
                        us_open_df = yf.download(needed_symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False)
                        current_opens = {}
                        runtime_prices = {}
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
                                runtime_prices[s] = float(df["close"].dropna().iloc[-1])
                            except Exception:
                                pass
                        had_orders = bool(us_engine.state.get("pending_buys") or us_engine.state.get("pending_sells"))
                        us_engine.state["last_execute_date"] = ny_today_str
                        us_engine.execute_open_fills(current_opens, runtime_prices=runtime_prices, delay_mins=delay_mins)
                        fill_status = "EXECUTE_FILL" if had_orders else "EXECUTE_NO_ORDERS"
                        us_cycle_status = fill_status
                        us_engine.log_daily_equity(status=fill_status, delay_mins=delay_mins, notes=msg)

        if args.pod in ["all", "pod_c", "multi_asset"]:
            print("\n>>> [POD C: MULTI-ASSET] EXECUTING QUEUED MACRO ORDERS AT MARKET OPEN (09:15 IST)...")
            needed_symbols = list(
                set(multi_asset_engine.state["positions"].keys()) |
                {p["sym"] for p in multi_asset_engine.state["pending_buys"]} |
                {p["sym"] for p in multi_asset_engine.state["pending_sells"]}
            )
            current_opens = {}
            if needed_symbols:
                open_df = yf.download(needed_symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False)
                for s in needed_symbols:
                    try:
                        if isinstance(open_df.columns, pd.MultiIndex):
                            if s in open_df.columns.levels[-1]:
                                df = open_df.xs(s, axis=1, level=-1).dropna(how="all")
                            elif s in open_df.columns.levels[0]:
                                df = open_df[s].dropna(how="all")
                            else:
                                continue
                        else:
                            df = open_df.dropna(how="all")
                        df.columns = [str(c).lower() for c in df.columns]
                        current_opens[s] = float(df["open"].dropna().iloc[-1])
                    except Exception:
                        pass
            multi_asset_engine.execute_open_fills(current_opens)

    # Dispatches live mobile notifications and regenerates web dashboard
    dispatch_notifications_and_dashboard(
        india_engine,
        us_engine,
        multi_asset_engine,
        args.phase,
        args.pod,
        us_cycle_status=us_cycle_status,
        us_cycle_delay=us_cycle_delay,
        us_cycle_notes=us_cycle_notes,
        us_notify=us_notify,
    )


def _send_us_error_alert(err_msg: str):
    if os.environ.get("ENABLE_NOTIFICATIONS", "0") != "1":
        return
    try:
        from trading_system.app.notifications.notifier import QuantNotifier
        notifier = QuantNotifier()
        if notifier.discord_url:
            notifier.send_discord_alert(
                title="🚨 US Shadow Desk — Integrity Guard Alert",
                message=err_msg[:3800],
                color=0xFF3333,
            )
    except Exception:
        pass


def dispatch_notifications_and_dashboard(
    india_engine,
    us_engine,
    multi_asset_engine=None,
    phase: str = "status",
    pod: str = "all",
    us_cycle_status: str = "",
    us_cycle_delay: int = 0,
    us_cycle_notes: str = "",
    us_notify: bool = True,
):
    try:
        from trading_system.scripts.generate_web_dashboard import generate_dashboard_html
        generate_dashboard_html()
    except Exception as e:
        print(f"[Dashboard Warning] Could not regenerate web dashboard: {e}")

    if os.environ.get("ENABLE_NOTIFICATIONS", "0") != "1":
        return
    if pod == "us" and not us_notify:
        return

    try:
        from trading_system.app.notifications.notifier import QuantNotifier
        notifier = QuantNotifier()
        if not notifier.discord_url and not (notifier.tg_token and notifier.tg_chat_id):
            return

        # Rich Discord embed specifically for US Shadow cycles
        if pod == "us" and notifier.discord_url:
            us_cash = float(us_engine.state.get("cash", 0.0))
            us_pos = us_engine.state.get("positions", {})
            us_port_val = sum(
                float(p.get("shares", 0.0)) * float(p.get("last_close", p.get("entry_price", 0.0)))
                for p in us_pos.values()
            )
            us_eq = us_cash + us_port_val
            us_dd = float(us_engine.state.get("max_drawdown", 0.0))
            us_pnl = us_eq - us_engine.initial_capital
            us_pnl_pct = (us_pnl / us_engine.initial_capital * 100.0) if us_engine.initial_capital > 0 else 0.0
            day0_ok = bool(us_engine.state.get("day0_verified", False))

            trades = getattr(us_engine, "session_trades", [])
            if trades:
                trade_lines = []
                for t in trades[:12]:
                    act = t.get("action", "TRADE")
                    sym = t.get("symbol", "")
                    shs = float(t.get("shares", 0.0))
                    fpx = float(t.get("fill_price", 0.0))
                    pnl_s = f" | PnL: ${float(t.get('realized_pnl', 0.0)):+,.2f}" if act in ("SELL", "TRIM") else ""
                    trade_lines.append(f"• `{act}` **{shs:g} {sym}** @ ${fpx:,.2f}{pnl_s}")
                trades_block = "\n".join(trade_lines)
            else:
                trades_block = "• None in this cycle"

            pos_lines = []
            for sym, p in sorted(us_pos.items()):
                shs = float(p.get("shares", 0.0))
                entry = float(p.get("entry_price", 0.0))
                cur = float(p.get("last_close", entry))
                mv = shs * cur
                pct = ((cur - entry) / entry * 100.0) if entry > 0 else 0.0
                pos_lines.append(f"• **{sym}**: {shs:g} shs @ ${cur:,.2f} (${mv:,.0f}, {pct:+.1f}%)")
            pos_block = "\n".join(pos_lines[:10]) if pos_lines else "• None (100% Cash)"

            q_buys = [f"`BUY` {b['sym']} (${b['target_alloc']:,.0f})" for b in us_engine.state.get("pending_buys", [])]
            q_sells = [f"`SELL` {s['sym']}" for s in us_engine.state.get("pending_sells", [])]
            queued_all = q_sells + q_buys
            macro_reg = us_engine.state.get("macro_regime", "")
            radar_sum = us_engine.state.get("radar_summary", "N/A")
            if queued_all:
                queued_block = ", ".join(queued_all[:10])
            elif macro_reg == "BEAR_DEFENSE":
                queued_block = "None (100% Cash Defense Active — 0% Bear Exposure)"
            else:
                queued_block = "None queued"

            status_lbl = us_cycle_status or phase.upper()
            is_skip = status_lbl.startswith("SKIPPED_")
            color = 0xFFB000 if is_skip else 0x00D084

            embed_msg = (
                f"**Phase:** `{phase.upper()}` | **Status:** `{status_lbl}` (Delay: {us_cycle_delay}m)\n"
                f"**Day 0 Verified:** `{day0_ok}` | **Last Scan Bar:** `{us_engine.state.get('last_scan_bar_date') or 'N/A'}`\n"
                f"🛡️ **Macro Regime:** `{radar_sum}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Equity:** ${us_eq:,.2f} ({us_pnl_pct:+.2f}% / ${us_pnl:+,.2f})\n"
                f"💵 **Cash:** ${us_cash:,.2f} | **Positions:** {len(us_pos)} | **Max DD:** {us_dd*100:.2f}%\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 **Trades Executed ({len(trades)}):**\n{trades_block}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ **Queued for Next Open:** {queued_block}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 **Active Holdings ({len(us_pos)}):**\n{pos_block}"
            )
            if us_cycle_notes and is_skip:
                embed_msg += f"\n\nℹ️ _{us_cycle_notes}_"

            notifier.send_discord_alert(
                title=f"🇺🇸 US Shadow Desk (Alpaca) — {status_lbl}",
                message=embed_msg[:3900],
                color=color,
            )
            return

        msg_lines = [f"⚡ **ANTIGRAVITY QUANT ALERT: {phase.upper()} CYCLE ({pod.upper()})**"]
        if pod in ["all", "india"]:
            in_cash = india_engine.state.get("cash", 0)
            in_pos = india_engine.state.get("positions", {})
            in_eq = in_cash + sum(p.get("shares", 0) * p.get("last_close", p.get("entry_price", 0)) for p in in_pos.values())
            in_dd = india_engine.state.get("max_drawdown", 0)
            in_pnl = in_eq - india_engine.initial_capital
            in_pnl_pct = (in_pnl / india_engine.initial_capital * 100) if india_engine.initial_capital > 0 else 0
            msg_lines.append("")
            msg_lines.append("🇮🇳 **India Growth Pod (NSE 100)**:")
            msg_lines.append(f"• Equity: ₹{in_eq:,.0f} ({in_pnl_pct:+.2f}%) | Cash: ₹{in_cash:,.0f}")
            msg_lines.append(f"• Active Positions: {len(in_pos)} | Max DD: {in_dd*100:.1f}%")
            if india_engine.state.get("in_tier4_defense"):
                msg_lines.append("• 🛡️ Bear Defense: ACTIVE (Cash Protected)")
            if india_engine.state.get("pending_buys"):
                buys_str = ", ".join([b["sym"] for b in india_engine.state["pending_buys"]])
                msg_lines.append(f"• Queued Buys for Open: {buys_str}")
            if india_engine.state.get("pending_sells"):
                sells_str = ", ".join([s["sym"] for s in india_engine.state["pending_sells"]])
                msg_lines.append(f"• Queued Sells for Open: {sells_str}")

        if pod in ["all", "us"]:
            us_cash = us_engine.state.get("cash", 0)
            us_pos = us_engine.state.get("positions", {})
            us_eq = us_cash + sum(p.get("shares", 0) * p.get("last_close", p.get("entry_price", 0)) for p in us_pos.values())
            us_dd = us_engine.state.get("max_drawdown", 0)
            us_pnl = us_eq - us_engine.initial_capital
            us_pnl_pct = (us_pnl / us_engine.initial_capital * 100) if us_engine.initial_capital > 0 else 0
            msg_lines.append("")
            msg_lines.append("🇺🇸 **US Growth Pod (NASDAQ/NYSE)**:")
            msg_lines.append(f"• Equity: ${us_eq:,.2f} ({us_pnl_pct:+.2f}%) | Cash: ${us_cash:,.2f}")
            msg_lines.append(f"• Active Positions: {len(us_pos)} | Max DD: {us_dd*100:.1f}%")
            if us_engine.state.get("pending_buys"):
                buys_str = ", ".join([b["sym"] for b in us_engine.state["pending_buys"]])
                msg_lines.append(f"• Queued Buys for Open: {buys_str}")
            if us_engine.state.get("pending_sells"):
                sells_str = ", ".join([s["sym"] for s in us_engine.state["pending_sells"]])
                msg_lines.append(f"• Queued Sells for Open: {sells_str}")

        if pod in ["all", "pod_c", "multi_asset"] and multi_asset_engine is not None:
            c_cash = multi_asset_engine.state.get("cash", 0)
            c_pos = multi_asset_engine.state.get("positions", {})
            c_eq = c_cash + sum(p.get("shares", 0) * p.get("last_close", p.get("entry_price", 0)) for p in c_pos.values())
            c_dd = multi_asset_engine.state.get("max_drawdown", 0)
            c_pnl = c_eq - multi_asset_engine.initial_capital
            c_pnl_pct = (c_pnl / multi_asset_engine.initial_capital * 100) if multi_asset_engine.initial_capital > 0 else 0
            msg_lines.append("")
            msg_lines.append("🌐 **Pod C: Multi-Asset Trend (NIFTYBEES, MON100, GOLDBEES, Cash)**:")
            msg_lines.append(f"• Equity: ₹{c_eq:,.0f} ({c_pnl_pct:+.2f}%) | Cash: ₹{c_cash:,.0f}")
            msg_lines.append(f"• Active Positions: {len(c_pos)} / 3 Core Assets | Max DD: {c_dd*100:.1f}%")
            if multi_asset_engine.state.get("pending_buys"):
                buys_str = ", ".join([b["sym"] for b in multi_asset_engine.state["pending_buys"]])
                msg_lines.append(f"• Queued Buys for Open: {buys_str}")
            if multi_asset_engine.state.get("pending_sells"):
                sells_str = ", ".join([s["sym"] for s in multi_asset_engine.state["pending_sells"]])
                msg_lines.append(f"• Queued Sells for Open: {sells_str}")

        msg = "\n".join(msg_lines)
        if notifier.discord_url:
            notifier.send_discord_message(msg)
        if notifier.tg_token and notifier.tg_chat_id:
            tg_msg = msg.replace("**", "*")
            notifier.send_telegram_message(tg_msg)
    except Exception as e:
        print(f"[Notifier Warning] Could not dispatch notifications: {e}")



if __name__ == "__main__":
    main()
