"""
Specialist Bot 1: ETF and Gold Execution Bot (Phase 1 Champion)
================================================================
Governs Gate B 13-Week Paper Incubation on NSE India with INR 80,000 capital.
Governing Protocols:
  - Base Protocol: PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112 (SHA-256: 2434e15b...)
  - Amendment V1.1: AMENDMENT-ETF-GOLD-BONDS-V1-1-20261114 (SHA-256: d49b3b44...)

Champion Strategy (Static 5-Asset Mix with Sovereign Gilts):
  - 25.0% GOLDBEES.NS: Physical Domestic Gold ETF (Precious metals inflation hedge)
  - 25.0% MON100.NS: Nasdaq 100 ETF (US secular innovation & tech growth)
  - 15.0% NIFTYBEES.NS: Nifty 50 ETF (India large-cap core compounder)
  - 15.0% MID150BEES.NS / MIDCAPETF.NS: Nifty Midcap 150 ETF (India mid-cap compounder)
  - 20.0% LTGILTBEES.NS / LIQUIDBEES.NS: Sovereign Gilt & Cash Sleeve

Audited Performance (Gate A Sealed Historical & Holdout Verification):
  - In-Sample (2007-09-24 to 2024-12-31, 4,494 Sessions, Zero bfill lookahead):
      CAGR: 15.15% | Max Drawdown: -25.59% | Sharpe Ratio: 0.75 | Trades/Yr: 4.1
  - Out-of-Sample Holdout (2025-01-01 to Present, 463 Sessions on Live NSE ETFs):
      CAGR: 16.49% | Max Drawdown: -11.90% | Sharpe Ratio: 0.88 | Trades/Yr: 5.4
  - Dynamic 200-SMA Trend Rotation failed Gate A (10.67% CAGR, -17.12% MaxDD, 0.59 Sharpe, 34.5 trades/yr)
    and is formally retired for Phase 1.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import StrategyInterface

logger = logging.getLogger("ETFGoldsBot")

# Canonical 5-Asset Universe with Gilt Sleeve
DEFAULT_UNIVERSE = ["GOLDBEES.NS", "MON100.NS", "NIFTYBEES.NS", "MID150BEES.NS", "LTGILTBEES.NS"]
DEFAULT_TARGET_WEIGHTS = {
    "GOLDBEES.NS": 0.25,
    "MON100.NS": 0.25,
    "NIFTYBEES.NS": 0.15,
    "MID150BEES.NS": 0.15,
    "LTGILTBEES.NS": 0.20
}
ALTERNATIVE_SYMBOLS = {
    "MID150BEES.NS": "MIDCAPETF.NS"  # Liquid Mirae Asset Midcap 150 ETF fallback
}

DEFAULT_CAPITAL = 80000.0  # INR 80,000 (Mandatory Phase 1 starting capital)
INCUBATION_TARGET_WEEKS = 13
INCUBATION_TARGET_DAYS = INCUBATION_TARGET_WEEKS * 7
DRIFT_BAND_THRESHOLD = 0.05  # 5 percentage points absolute drift triggers rebalance
MAX_PRICE_STALENESS_DAYS = 5  # Max calendar days since last trade bar before stale-abort

# Transaction friction parameters (Dhan delivery schedule)
FLAT_DP_FEE = 14.75          # Flat Rs 14.75 per sale scrip
STAMP_DUTY_BUY_BPS = 1.5      # 0.015% on buys
EXCHANGE_FEES_BPS = 0.35      # Exchange turnover + SEBI + GST
SLIPPAGE_BPS = 5.0            # 5 bps conservative execution slippage
STT_EQUITY_SELL_BPS = 10.0    # 0.10% STT on equity delivery sales


class ETFGoldsStrategy(StrategyInterface):
    """
    Implements the StrategyInterface for Bot 1 (ETF and Gold Bot).
    Allocates target weights to the 5 core macro pillars (including 20% Gilt sleeve).
    """
    def __init__(self, target_weights: Optional[Dict[str, float]] = None):
        self.target_weights = target_weights or DEFAULT_TARGET_WEIGHTS.copy()
        self.current_risk_status: Dict[str, Any] = {
            "regime": "ACTIVE_CHAMPION_ALLOCATION",
            "weights": self.target_weights,
            "drift_band_threshold": DRIFT_BAND_THRESHOLD
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
    Enforces yearly calendar rebalancing, 5% drift-band rebalancing,
    stale price guards, and fail-closed safety.
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
                logger.error(f"Error reading state file: {e}. Reinitializing clean state.")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "bot_name": "ETF_AND_GOLD_BOT",
            "phase": "PHASE_1",
            "gate": "GATE_B_PAPER",
            "incubation_start_date": now_iso,
            "incubation_target_weeks": INCUBATION_TARGET_WEEKS,
            "days_incubated": 0,
            "initial_capital": self.initial_capital,
            "cash": self.initial_capital,
            "positions": {},  # sym -> {shares: int, avg_price: float, last_price: float, entry_date: str}
            "nav": self.initial_capital,
            "hwm": self.initial_capital,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "last_run_timestamp": None,
            "last_rebalance_date": None,
            "status": "HEALTHY_ACTIVE"
        }

    def _save_state(self):
        self.state["last_run_timestamp"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def log_trade(
        self,
        symbol: str,
        side: str,
        shares: int,
        price: float,
        total_cost: float,
        fees: float,
        tax: float = 0.0
    ):
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
            "tax_paid": round(tax, 2),
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

        # Calculate incubation days from incubation_start_date
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

    def fetch_current_quotes(self, symbols: List[str]) -> Tuple[Dict[str, float], List[str]]:
        """
        Fetches latest closing prices using yfinance.
        Enforces stale-price guard (<= 5 calendar days old).
        Returns: (quotes_dict, list_of_stale_or_missing_symbols)
        """
        quotes: Dict[str, float] = {}
        stale_or_missing: List[str] = []
        now_dt = datetime.now(timezone.utc)

        for sym in symbols:
            lookup_sym = sym
            try:
                t = yf.Ticker(lookup_sym)
                hist = t.history(period="10d")
                if hist.empty and sym in ALTERNATIVE_SYMBOLS:
                    lookup_sym = ALTERNATIVE_SYMBOLS[sym]
                    t = yf.Ticker(lookup_sym)
                    hist = t.history(period="10d")

                if not hist.empty:
                    last_bar = hist.iloc[-1]
                    bar_dt = hist.index[-1].to_pydatetime()
                    if bar_dt.tzinfo is None:
                        bar_dt = bar_dt.replace(tzinfo=timezone.utc)

                    days_old = (now_dt - bar_dt).days
                    last_price = float(last_bar["Close"])

                    # Stale-price guard
                    if days_old > MAX_PRICE_STALENESS_DAYS:
                        logger.error(f"Stale quote detected for {sym}: Bar date {bar_dt.date()} is {days_old} days old!")
                        stale_or_missing.append(f"{sym} (STALE: {days_old}d old)")
                    elif last_price <= 0 or pd.isna(last_price):
                        stale_or_missing.append(f"{sym} (INVALID_PRICE: {last_price})")
                    else:
                        quotes[sym] = last_price
                else:
                    stale_or_missing.append(f"{sym} (EMPTY_HISTORY)")
            except Exception as e:
                logger.error(f"Failed to fetch quote for {sym}: {e}")
                stale_or_missing.append(f"{sym} (ERROR: {str(e)[:30]})")

        return quotes, stale_or_missing

    def evaluate_rebalance_trigger(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        current_date: datetime
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a portfolio rebalance is triggered:
        1. Opening allocation (zero positions held)
        2. Yearly calendar rebalance (final trading session of the year)
        3. Drift band trigger: any asset weight drifts > 5 percentage points from target
        """
        if not self.state["positions"]:
            return True, "INITIAL_OPENING_ALLOCATION"

        # Check drift band
        for sym, target_w in target_weights.items():
            curr_w = current_weights.get(sym, 0.0)
            drift = abs(curr_w - target_w)
            if drift > DRIFT_BAND_THRESHOLD:
                return True, f"DRIFT_BAND_TRIGGER: {sym} drifted by {drift*100:.1f}% (> {DRIFT_BAND_THRESHOLD*100:.0f}%)"

        # Check calendar year-end rebalance
        last_rebal = self.state.get("last_rebalance_date")
        if last_rebal is not None:
            last_rebal_year = datetime.fromisoformat(last_rebal).year
            if current_date.year > last_rebal_year and current_date.month == 12:
                return True, f"CALENDAR_YEARLY_REBALANCE: Year {current_date.year}"

        return False, "TARGET_WEIGHTS_ALIGNED_WITHIN_BAND"

    def run_daily_cycle(self, quotes: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Executes daily evaluation, drift monitoring, rebalancing, and state persistence.
        Fails closed on any missing or stale quote.
        """
        target_weights = self.strategy.evaluate_allocations(
            current_date=pd.Timestamp.now(timezone.utc),
            market_data={},
            portfolio_state=self.state
        )
        symbols = list(target_weights.keys())
        stale_symbols: List[str] = []

        if quotes is None:
            quotes, stale_symbols = self.fetch_current_quotes(symbols)

        # Fail-closed guard: all 5 assets must have valid, fresh quotes
        missing = [sym for sym in symbols if sym not in quotes or quotes[sym] <= 0]
        if missing or stale_symbols:
            logger.error(f"Fail-closed: Missing/stale quotes detected: {missing + stale_symbols}. Aborting cycle without trading.")
            return {
                "status": "FAIL_CLOSED",
                "missing_quotes": missing,
                "stale_quotes": stale_symbols,
                "nav": self.state["nav"]
            }

        # Update position current prices and calculate holdings value
        for sym in self.state["positions"]:
            if sym in quotes:
                self.state["positions"][sym]["last_price"] = quotes[sym]

        holdings_value = sum(
            pos["shares"] * quotes[sym]
            for sym, pos in self.state["positions"].items()
            if sym in quotes
        )
        total_nav = self.state["cash"] + holdings_value

        # Calculate current weights
        current_weights = {
            sym: (self.state["positions"][sym]["shares"] * quotes[sym]) / total_nav
            if sym in self.state["positions"] and total_nav > 0 else 0.0
            for sym in symbols
        }

        now_dt = datetime.now(timezone.utc)
        should_rebal, rebal_reason = self.evaluate_rebalance_trigger(current_weights, target_weights, now_dt)

        if should_rebal:
            logger.info(f"Rebalance triggered: {rebal_reason}")

            # 1. Sells first to free cash
            for sym, target_w in target_weights.items():
                target_val = total_nav * target_w
                curr_val = self.state["positions"].get(sym, {}).get("shares", 0) * quotes[sym]
                diff = target_val - curr_val

                if diff < -50.0 and sym in self.state["positions"]:  # Trim excess
                    pos = self.state["positions"][sym]
                    sh_to_sell = int(abs(diff) // quotes[sym])
                    if sh_to_sell > 0:
                        trade_val = sh_to_sell * quotes[sym]
                        slip = trade_val * (SLIPPAGE_BPS / 10000.0)
                        dp = FLAT_DP_FEE
                        stt = trade_val * (STT_EQUITY_SELL_BPS / 10000.0) if sym in ["NIFTYBEES.NS", "MID150BEES.NS"] else 0.0
                        exch = trade_val * (EXCHANGE_FEES_BPS / 10000.0)
                        total_fees = slip + dp + stt + exch

                        # Capital gains tax calculation
                        entry_px = pos.get("entry_price", quotes[sym])
                        gain = (quotes[sym] - entry_px) * sh_to_sell
                        tax = 0.0
                        if gain > 0:
                            entry_dt_str = pos.get("entry_date", now_dt.strftime("%Y-%m-%d"))
                            try:
                                h_days = (now_dt.date() - datetime.strptime(entry_dt_str, "%Y-%m-%d").date()).days
                            except Exception:
                                h_days = 0
                            tax_rate = 0.125 if h_days >= 365 else 0.15
                            tax = gain * tax_rate

                        proceeds = trade_val - total_fees - tax
                        self.state["cash"] += proceeds
                        pos["shares"] -= sh_to_sell
                        if pos["shares"] <= 0:
                            del self.state["positions"][sym]
                        self.log_trade(sym, "SELL", sh_to_sell, quotes[sym], proceeds, total_fees, tax)
                        logger.info(f"Sold {sh_to_sell} shs of {sym} @ INR {quotes[sym]:.2f} (Proceeds: INR {proceeds:.2f})")

            # 2. Buys second using available cash
            for sym, target_w in target_weights.items():
                target_val = total_nav * target_w
                curr_val = self.state["positions"].get(sym, {}).get("shares", 0) * quotes[sym]
                diff = target_val - curr_val

                if diff > 50.0 and self.state["cash"] > 100.0:
                    px = quotes[sym]
                    alloc = min(diff, self.state["cash"] * 0.98)
                    sh_to_buy = int(alloc // (px * (1 + (SLIPPAGE_BPS + STAMP_DUTY_BUY_BPS + EXCHANGE_FEES_BPS) / 10000.0)))
                    if sh_to_buy > 0:
                        trade_val = sh_to_buy * px
                        slip = trade_val * (SLIPPAGE_BPS / 10000.0)
                        stamp = trade_val * (STAMP_DUTY_BUY_BPS / 10000.0)
                        exch = trade_val * (EXCHANGE_FEES_BPS / 10000.0)
                        total_fees = slip + stamp + exch
                        total_cost = trade_val + total_fees

                        if self.state["cash"] >= total_cost:
                            self.state["cash"] -= total_cost
                            if sym not in self.state["positions"]:
                                self.state["positions"][sym] = {
                                    "shares": sh_to_buy,
                                    "entry_price": px,
                                    "last_price": px,
                                    "entry_date": now_dt.strftime("%Y-%m-%d")
                                }
                            else:
                                pos = self.state["positions"][sym]
                                prev_sh = pos["shares"]
                                pos["shares"] += sh_to_buy
                                pos["entry_price"] = ((prev_sh * pos["entry_price"]) + (sh_to_buy * px)) / pos["shares"]
                                pos["last_price"] = px

                            self.log_trade(sym, "BUY", sh_to_buy, px, total_cost, total_fees, 0.0)
                            logger.info(f"Bought {sh_to_buy} shs of {sym} @ INR {px:.2f} (Cost: INR {total_cost:.2f})")

            self.state["last_rebalance_date"] = now_dt.isoformat()

        # Update NAV, HWM, drawdown, and incubation days
        self.log_equity(quotes)
        self._save_state()

        return {
            "status": "SUCCESS",
            "nav": self.state["nav"],
            "cash": self.state["cash"],
            "positions": self.state["positions"],
            "current_weights": current_weights,
            "rebalance_executed": should_rebal,
            "rebalance_reason": rebal_reason,
            "current_drawdown_pct": self.state.get("current_drawdown_pct", 0.0),
            "max_drawdown_pct": self.state.get("max_drawdown_pct", 0.0),
            "days_incubated": self.state["days_incubated"],
            "weeks_incubated": round(self.state["days_incubated"] / 7.0, 1),
            "incubation_progress_pct": round(min(100.0, (self.state["days_incubated"] / INCUBATION_TARGET_DAYS) * 100.0), 1)
        }
