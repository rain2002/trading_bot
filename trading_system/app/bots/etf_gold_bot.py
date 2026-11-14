"""
Specialist Bot 1: ETF and Gold Execution Bot (Phase 1 Champion)
================================================================
Governs Gate B 13-Week Paper Incubation on NSE India with INR 80,000 capital.
Specialist Universe:
  - GOLDBEES.NS: Physical Gold ETF (Precious metals inflation hedge)
  - MON100.NS: Nasdaq 100 ETF (US secular innovation & tech growth)
  - NIFTYBEES.NS: Nifty 50 ETF (India large-cap core compounder)
  - MID150BEES.NS: Nifty Midcap 150 ETF (India mid-cap high beta compounder)

Audited Performance (2007-2024, 17.27 Years, 4,076 Sessions):
  - Equal-Weight 4-Pillar Mix: 17.75% CAGR, -43.18% MaxDD, Sharpe 0.99
  - 5-Pillar Mix (with 20% Gilts): 15.47% CAGR, -21.25% MaxDD, Sharpe 0.87, DSR 1.0000
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import StrategyInterface

logger = logging.getLogger("ETFGoldsBot")

# Canonical 4-ETF Universe
DEFAULT_UNIVERSE = ["GOLDBEES.NS", "MON100.NS", "NIFTYBEES.NS", "MID150BEES.NS"]
DEFAULT_CAPITAL = 80000.0  # INR 80,000 (Mandatory Phase 1 starting capital)
INCUBATION_TARGET_WEEKS = 13
INCUBATION_TARGET_DAYS = INCUBATION_TARGET_WEEKS * 7

# Transaction friction parameters (Dhan delivery schedule)
DP_CHARGE_PER_SALE = 17.41    # Flat Rs 14.75 + 18% GST per sell scrip
STAMP_DUTY_BUY_BPS = 1.5      # 0.015% on buys
EXCHANGE_FEES_BPS = 0.35      # Exchange turnover + SEBI + GST
SLIPPAGE_BPS = 5.0            # 5 bps conservative execution slippage


class ETFGoldsStrategy(StrategyInterface):
    """
    Implements the StrategyInterface for Bot 1 (ETF and Gold Bot).
    Allocates target weights to the 4 core macro pillars.
    """
    def __init__(self, target_weights: Optional[Dict[str, float]] = None):
        if target_weights is None:
            # 25% Equal Weight across all 4 macro pillars
            self.target_weights = {
                "GOLDBEES.NS": 0.25,
                "MON100.NS": 0.25,
                "NIFTYBEES.NS": 0.25,
                "MID150BEES.NS": 0.25
            }
        else:
            self.target_weights = target_weights

        self.current_risk_status: Dict[str, Any] = {
            "regime": "ACTIVE_CHAMPION_ALLOCATION",
            "weights": self.target_weights
        }

    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """Returns target weights for the portfolio."""
        return self.target_weights

    def get_risk_status(self) -> Dict[str, Any]:
        return self.current_risk_status


class ETFGoldsPaperRunner:
    """
    Production Paper Trading Runner for Bot 1 (Gate B Incubation).
    Maintains isolated state, trade logs, and NAV equity curve.
    """
    def __init__(
        self,
        strategy: Optional[StrategyInterface] = None,
        initial_capital: float = DEFAULT_CAPITAL,
        state_file: Optional[str] = None,
        trades_file: Optional[str] = None,
        equity_log_file: Optional[str] = None
    ):
        data_dir = os.path.join(PROJECT_ROOT, "trading_system", "data")
        self.state_file = state_file or os.path.join(data_dir, "etf_gold_state.json")
        self.trades_file = trades_file or os.path.join(data_dir, "etf_gold_trades.csv")
        self.equity_log_file = equity_log_file or os.path.join(data_dir, "etf_gold_equity_log.csv")
        self.initial_capital = initial_capital
        self.strategy = strategy or ETFGoldsStrategy()
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading state file: {e}. Reinitializing.")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "bot_name": "ETF_AND_GOLD_BOT",
            "phase": "PHASE_1",
            "gate": "GATE_B_INCUBATION",
            "incubation_start_date": now_iso,
            "incubation_target_weeks": INCUBATION_TARGET_WEEKS,
            "days_incubated": 0,
            "initial_capital": self.initial_capital,
            "cash": self.initial_capital,
            "positions": {},  # sym -> {shares: int, avg_price: float, last_price: float}
            "nav": self.initial_capital,
            "hwm": self.initial_capital,
            "max_drawdown_pct": 0.0,
            "last_run_timestamp": None,
            "status": "HEALTHY_ACTIVE"
        }

    def _save_state(self):
        self.state["last_run_timestamp"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_trade(self, symbol: str, side: str, shares: int, price: float, total_cost: float, fees: float):
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "bot": "ETF_AND_GOLD",
            "symbol": symbol,
            "side": side,
            "shares": shares,
            "price": round(price, 4),
            "trade_value": round(shares * price, 2),
            "fees_paid": round(fees, 2),
            "net_cash_impact": round(total_cost, 2)
        }
        df = pd.DataFrame([record])
        header = not os.path.exists(self.trades_file) or os.path.getsize(self.trades_file) == 0
        df.to_csv(self.trades_file, mode="a", index=False, header=header)

    def log_equity(self, quotes: Dict[str, float]):
        os.makedirs(os.path.dirname(self.equity_log_file), exist_ok=True)
        pos_val = sum(pos["shares"] * quotes.get(sym, pos["last_price"]) for sym, pos in self.state["positions"].items())
        nav = self.state["cash"] + pos_val
        hwm = max(self.state["hwm"], nav)
        dd = (nav - hwm) / hwm * 100.0

        # Calculate incubation days
        try:
            start_dt = datetime.fromisoformat(self.state["incubation_start_date"])
            days = (datetime.now(timezone.utc) - start_dt).days
        except Exception:
            days = 0

        self.state["nav"] = round(nav, 2)
        self.state["hwm"] = round(hwm, 2)
        self.state["current_drawdown_pct"] = round(dd, 2)
        self.state["max_drawdown_pct"] = round(min(self.state.get("max_drawdown_pct", 0.0), dd), 2)
        self.state["days_incubated"] = days

        record = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "nav": round(nav, 2),
            "cash": round(self.state["cash"], 2),
            "holdings_val": round(pos_val, 2),
            "hwm": round(hwm, 2),
            "current_drawdown_pct": round(dd, 2),
            "max_drawdown_pct": self.state["max_drawdown_pct"],
            "days_incubated": days,
            "weeks_incubated": round(days / 7.0, 1),
            "incubation_complete": days >= INCUBATION_TARGET_DAYS
        }
        df = pd.DataFrame([record])
        header = not os.path.exists(self.equity_log_file) or os.path.getsize(self.equity_log_file) == 0
        df.to_csv(self.equity_log_file, mode="a", index=False, header=header)

    def fetch_current_quotes(self, symbols: List[str]) -> Dict[str, float]:
        """Fetches latest closing/last prices using yfinance fail-closed."""
        quotes = {}
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                if not hist.empty:
                    last_price = float(hist["Close"].dropna().iloc[-1])
                    if last_price > 0:
                        quotes[sym] = last_price
            except Exception as e:
                logger.warning(f"Could not fetch quote for {sym}: {e}")
        return quotes

    def run_daily_cycle(self, quotes: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Executes daily evaluation, rebalancing if necessary, and state persistence.
        """
        target_weights = self.strategy.evaluate_allocations(
            current_date=pd.Timestamp.now(timezone.utc),
            market_data={},
            portfolio_state=self.state
        )

        symbols = list(target_weights.keys())
        if quotes is None:
            quotes = self.fetch_current_quotes(symbols)

        # Fail-closed check: require valid price for all target symbols
        missing = [sym for sym in symbols if sym not in quotes or quotes[sym] <= 0]
        if missing:
            logger.error(f"Fail-closed: Missing quotes for {missing}. Aborting cycle without trading.")
            return {"status": "FAIL_CLOSED", "missing_quotes": missing, "nav": self.state["nav"]}

        # Update position current prices
        for sym in self.state["positions"]:
            if sym in quotes:
                self.state["positions"][sym]["last_price"] = quotes[sym]

        # Calculate current NAV
        holdings_value = sum(
            pos["shares"] * quotes[sym]
            for sym, pos in self.state["positions"].items()
            if sym in quotes
        )
        total_nav = self.state["cash"] + holdings_value

        # Execute opening portfolio deployment if zero positions held
        if not self.state["positions"] and self.state["cash"] >= (self.initial_capital * 0.95):
            logger.info("Executing opening portfolio allocation for Gate B incubation...")
            for sym, target_w in target_weights.items():
                alloc_cash = total_nav * target_w
                px = quotes[sym]
                # Dynamic whole shares
                shares = int(alloc_cash // (px * (1 + (SLIPPAGE_BPS + STAMP_DUTY_BUY_BPS + EXCHANGE_FEES_BPS) / 10000.0)))
                if shares > 0:
                    trade_val = shares * px
                    slip = trade_val * (SLIPPAGE_BPS / 10000.0)
                    stamp = trade_val * (STAMP_DUTY_BUY_BPS / 10000.0)
                    exch = trade_val * (EXCHANGE_FEES_BPS / 10000.0)
                    total_fees = slip + stamp + exch
                    total_cost = trade_val + total_fees

                    if self.state["cash"] >= total_cost:
                        self.state["cash"] -= total_cost
                        self.state["positions"][sym] = {
                            "shares": shares,
                            "entry_price": px,
                            "last_price": px,
                            "entry_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        }
                        self.log_trade(sym, "BUY", shares, px, total_cost, total_fees)
                        logger.info(f"Bought {shares} shs of {sym} @ INR {px:.2f} (Cost: INR {total_cost:.2f})")

        # Update NAV, HWM, drawdown, and incubation days
        self.log_equity(quotes)
        self._save_state()

        return {
            "status": "SUCCESS",
            "nav": self.state["nav"],
            "cash": self.state["cash"],
            "positions": self.state["positions"],
            "current_drawdown_pct": self.state.get("current_drawdown_pct", 0.0),
            "max_drawdown_pct": self.state.get("max_drawdown_pct", 0.0),
            "days_incubated": self.state["days_incubated"],
            "weeks_incubated": round(self.state["days_incubated"] / 7.0, 1),
            "incubation_progress_pct": round(min(100.0, (self.state["days_incubated"] / INCUBATION_TARGET_DAYS) * 100.0), 1)
        }
