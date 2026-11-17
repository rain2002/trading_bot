"""
Specialist Bot 2: Bond and Cash Bot (Phase 3 Safe Carry Management)
===================================================================
Governs Gate B 13-Week Paper Incubation on NSE India with INR 20,000 capital.
Governing Protocol:
  - Base Protocol: PROTOCOL-BOND-AND-CASH-BOT-V1-20261114 (SHA-256: 21ca8098...)

Role and Mandate:
  - Safe parking of idle capital and cash inflows (SIP top-ups).
  - Defensive retreat destination when Central Portfolio Manager throttles or halts equity exposure.
  - Evaluated on a single question: Does it earn more than plain overnight cash without material drawdown?

Champion Strategy (B0 - 100% Overnight Cash Benchmark):
  - 100% LIQUIDBEES.NS (Overnight Cash Yield)
  - Zero duration risk, zero monthly drawdowns, immune to interest rate hikes.
  - Formally elected Champion under PROTOCOL-BOND-AND-CASH-BOT-V1-20261114 because candidates B1 and B2
    failed Gate A hurdles (B1 failed excess return hurdle at +0.36 pts vs +0.50 pts; B2 failed worst month
    hurdle at -3.03% vs -2.00% and bootstrap p5 at -0.31% vs > 0.0%). Per protocol rule, B0 ships by default.

Audited Performance (Gate A Sealed Historical & Holdout Verification):
  - In-Sample (2008-01-01 to 2024-12-31, 4,143 Sessions, Continuous 17-Year History):
      CAGR: 5.64% | Max Drawdown: 0.00% | Worst Month: +0.09% | Trades/Yr: 0.0
  - Out-of-Sample Holdout (2025-01-01 to Present, 463 Sessions on Live NSE ETFs):
      CAGR: 5.74% | Max Drawdown: 0.00% | Worst Month: +0.20% | Trades/Yr: 0.0

Manager Dynamic Linkage:
  - Ingests `max_duration_scale` (1.0 = normal, 0.0 = retreat/throttled).
  - When `max_duration_scale == 0.0`, duration exposure is forced to 0.0% (100% LIQUIDBEES.NS).
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

logger = logging.getLogger("BondCashBot")

DEFAULT_UNIVERSE = ["LIQUIDBEES.NS", "LTGILTBEES.NS"]
DEFAULT_CAPITAL = 20000.0  # INR 20,000 (Mandatory Phase 3 starting paper capital)
INCUBATION_TARGET_WEEKS = 13
INCUBATION_TARGET_DAYS = INCUBATION_TARGET_WEEKS * 7
DRIFT_BAND_THRESHOLD = 0.05  # 5 percentage points absolute drift triggers rebalance
MAX_PRICE_STALENESS_DAYS = 5  # Max calendar days since last trade bar before stale-abort

# Transaction friction parameters (Dhan delivery schedule for debt ETFs)
FLAT_DP_FEE = 14.75          # Flat Rs 14.75 per sale scrip
STAMP_DUTY_BUY_BPS = 1.5      # 0.015% on buys
EXCHANGE_FEES_BPS = 0.345     # Exchange turnover + SEBI + GST
SLIPPAGE_BPS = 5.0            # 5 bps conservative execution slippage
DEBT_STCG_TAX_RATE = 0.15     # Standard statutory short-term debt capital gains rate

# Cash Yield Parameters (Per PROTOCOL-BOND-AND-CASH-BOT-V1-20261114)
ANNUAL_REPO_RATE = 0.06       # 6.0% sovereign repo cash yield per protocol
LIQUIDBEES_TER = 0.0016       # 0.16% annual TER drag on cash ETF
# Daily net compounding rate across 252 trading sessions per year: (1 + 0.06 - 0.0016)^(1/252) - 1
DAILY_CARRY_RATE = (1.0 + ANNUAL_REPO_RATE - LIQUIDBEES_TER) ** (1.0 / 252.0) - 1.0


class BondCashB0Strategy(StrategyInterface):
    """
    B0 Strategy (Benchmark & Default):
    Always allocates 100% to overnight cash (LIQUIDBEES.NS).
    Zero duration risk.
    """
    def __init__(self):
        self.strategy_id = "B0"
        self.current_risk_status: Dict[str, Any] = {
            "strategy_id": "B0",
            "regime": "100_PCT_OVERNIGHT_CASH",
            "weights": {"LIQUIDBEES.NS": 1.0, "LTGILTBEES.NS": 0.0},
            "gilt_trend": "DISABLED"
        }

    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        return {"LIQUIDBEES.NS": 1.0, "LTGILTBEES.NS": 0.0}

    def get_risk_status(self) -> Dict[str, Any]:
        return self.current_risk_status


class BondCashB1Strategy(StrategyInterface):
    """
    B1 Strategy (Static Fixed-Weight Sleeve):
    Static 70% LIQUIDBEES.NS, 30% LTGILTBEES.NS.
    Subject to Manager's max_duration_scale override.
    """
    def __init__(self):
        self.strategy_id = "B1"
        self.current_risk_status: Dict[str, Any] = {
            "strategy_id": "B1",
            "regime": "STATIC_70_30_SPLIT",
            "base_target_gilt": 0.30,
            "drift_band_threshold": DRIFT_BAND_THRESHOLD
        }

    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        # Duration scale override from Central Portfolio Manager
        max_duration_scale = float(portfolio_state.get("max_duration_scale", 1.0))
        target_gilt = round(0.30 * max(0.0, min(1.0, max_duration_scale)), 4)
        target_cash = round(1.0 - target_gilt, 4)

        self.current_risk_status["max_duration_scale"] = max_duration_scale
        self.current_risk_status["target_weights"] = {
            "LIQUIDBEES.NS": target_cash,
            "LTGILTBEES.NS": target_gilt
        }
        return {"LIQUIDBEES.NS": target_cash, "LTGILTBEES.NS": target_gilt}

    def get_risk_status(self) -> Dict[str, Any]:
        return self.current_risk_status


class BondCashB2Strategy(StrategyInterface):
    """
    B2 Strategy (Trend-Gated Gilt Sleeve - Champion):
    70% LIQUIDBEES.NS + up to 30% LTGILTBEES.NS held only while LTGILTBEES.NS
    closes above its 200-day SMA, checked at month-end.
    If below 200-SMA, duration sleeve is de-allocated to 0% and 100% is parked in LIQUIDBEES.NS.
    Subject to Manager's max_duration_scale override.
    """
    def __init__(self, sma_lookback: int = 200):
        self.strategy_id = "B2"
        self.sma_lookback = sma_lookback
        self.current_risk_status: Dict[str, Any] = {
            "strategy_id": "B2",
            "regime": "TREND_GATED_GILT_SLEEVE",
            "sma_lookback": sma_lookback,
            "drift_band_threshold": DRIFT_BAND_THRESHOLD,
            "gilt_trend_bullish": False,
            "gilt_sma200": None,
            "gilt_last_close": None
        }

    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        max_duration_scale = float(portfolio_state.get("max_duration_scale", 1.0))
        
        # If manager forces retreat (max_duration_scale == 0.0), immediately park 100% in cash
        if max_duration_scale <= 0.0:
            self.current_risk_status["max_duration_scale"] = 0.0
            self.current_risk_status["gilt_trend_bullish"] = False
            return {"LIQUIDBEES.NS": 1.0, "LTGILTBEES.NS": 0.0}

        # Check 200-day SMA from market_data
        gilt_df = market_data.get("LTGILTBEES.NS")
        if gilt_df is None or gilt_df.empty:
            # Check GILT10Y or GILT proxy if LTGILTBEES not directly provided
            gilt_df = market_data.get("GILT10Y", market_data.get("GILT"))

        is_bullish = False
        sma_val = None
        last_close = None

        if gilt_df is not None and len(gilt_df) >= self.sma_lookback:
            close_col = "Close" if "Close" in gilt_df.columns else "close"
            closes = gilt_df[close_col].dropna()
            if len(closes) >= self.sma_lookback:
                sma_val = float(closes.rolling(window=self.sma_lookback).mean().iloc[-1])
                last_close = float(closes.iloc[-1])
                is_bullish = (last_close >= sma_val)
        elif gilt_df is not None and not gilt_df.empty:
            # If fewer bars than lookback, fall back to safe cash
            is_bullish = False

        self.current_risk_status["gilt_trend_bullish"] = is_bullish
        self.current_risk_status["gilt_sma200"] = round(sma_val, 4) if sma_val else None
        self.current_risk_status["gilt_last_close"] = round(last_close, 4) if last_close else None
        self.current_risk_status["max_duration_scale"] = max_duration_scale

        if is_bullish:
            target_gilt = round(0.30 * max(0.0, min(1.0, max_duration_scale)), 4)
            target_cash = round(1.0 - target_gilt, 4)
        else:
            target_gilt = 0.0
            target_cash = 1.0

        return {"LIQUIDBEES.NS": target_cash, "LTGILTBEES.NS": target_gilt}

    def get_risk_status(self) -> Dict[str, Any]:
        return self.current_risk_status


class BondCashPaperRunner:
    """
    Production Paper Trading Runner for Bot 2 (Gate B Paper Incubation).
    Maintains isolated state, trade logs, and NAV equity curve.
    Enforces yearly calendar rebalancing, 5% drift-band rebalancing,
    manager max_duration_scale retreat overrides, stale price guards,
    and fail-closed safety.
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
        self.state_file = state_file or os.path.join(data_dir, "bond_cash_state.json")
        self.trades_file = trades_file or os.path.join(data_dir, "bond_cash_trades.csv")
        self.equity_log_file = equity_log_file or os.path.join(data_dir, "bond_cash_equity_log.csv")
        self.initial_capital = float(initial_capital)
        self.strategy = strategy or BondCashB0Strategy()
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading bond cash state file: {e}. Reinitializing clean state.")

        now_iso = datetime.now(timezone.utc).isoformat()
        strategy_id = getattr(self.strategy, "strategy_id", "B0")
        return {
            "bot_name": "BOND_AND_CASH_BOT",
            "phase": "PHASE_3",
            "gate": "GATE_B_PAPER",
            "strategy_id": strategy_id,
            "incubation_start_date": now_iso,
            "incubation_target_weeks": INCUBATION_TARGET_WEEKS,
            "days_incubated": 0,
            "initial_capital": self.initial_capital,
            "cash": self.initial_capital,
            "positions": {},  # sym -> {shares: int, avg_price: float, last_price: float, entry_date: str, entry_price: float}
            "nav": self.initial_capital,
            "hwm": self.initial_capital,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "max_duration_scale": 1.0,
            "total_carry_earned": 0.0,
            "last_carry_date": None,
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
            "bot": "BOND_AND_CASH",
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

        canonical_fields = [
            "timestamp", "nav", "cash", "holdings_val", "total_carry_earned",
            "hwm", "current_drawdown_pct", "max_drawdown_pct", "max_duration_scale",
            "days_incubated", "weeks_incubated", "incubation_complete"
        ]

        # Automatic schema migration guard for bond_cash_equity_log.csv
        if os.path.exists(self.equity_log_file) and os.path.getsize(self.equity_log_file) > 0:
            try:
                import csv
                with open(self.equity_log_file, "r", encoding="utf-8") as f:
                    reader = list(csv.reader(f))
                if reader:
                    header = [c.strip() for c in reader[0]]
                    if "total_carry_earned" not in header:
                        migrated_rows = []
                        for row in reader[1:]:
                            if not row:
                                continue
                            if len(row) >= 11:
                                # Old layout: timestamp(0), nav(1), cash(2), holdings_val(3), hwm(4)...
                                new_row = row[:4] + ["0.0"] + row[4:]
                                migrated_rows.append(new_row)
                        with open(self.equity_log_file, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerow(canonical_fields)
                            writer.writerows(migrated_rows)
            except Exception as e:
                logger.error(f"Failed to check/migrate bond cash equity log schema: {e}")

        record = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "nav": round(nav, 2),
            "cash": round(self.state["cash"], 2),
            "holdings_val": round(pos_val, 2),
            "total_carry_earned": round(self.state.get("total_carry_earned", 0.0), 2),
            "hwm": round(hwm, 2),
            "current_drawdown_pct": round(dd, 2),
            "max_drawdown_pct": self.state["max_drawdown_pct"],
            "max_duration_scale": self.state.get("max_duration_scale", 1.0),
            "days_incubated": days,
            "weeks_incubated": round(days / 7.0, 1),
            "incubation_complete": days >= INCUBATION_TARGET_DAYS
        }
        session_date = str(record.get("timestamp", ""))[:10]
        if os.path.exists(self.equity_log_file) and os.path.getsize(self.equity_log_file) > 0:
            try:
                existing_df = pd.read_csv(self.equity_log_file, dtype=str)
                if "timestamp" in existing_df.columns:
                    mask = existing_df["timestamp"].str[:10] == session_date
                    if mask.any():
                        existing_df = existing_df[~mask]
                        new_df = pd.concat([existing_df, pd.DataFrame([record])[canonical_fields]], ignore_index=True)
                        new_df.to_csv(self.equity_log_file, index=False)
                        return
            except Exception as e:
                logger.warning(f"Error checking bond equity log for deduplication: {e}")

        df = pd.DataFrame([record])[canonical_fields]
        header = not os.path.exists(self.equity_log_file) or os.path.getsize(self.equity_log_file) == 0
        df.to_csv(self.equity_log_file, mode="a", index=False, header=header)

    def fetch_market_data(self, lookback_days: int = 300) -> Tuple[Dict[str, pd.DataFrame], Dict[str, float], List[str]]:
        """
        Fetches price history and latest quotes for DEFAULT_UNIVERSE.
        Returns: (market_data_dict, quotes_dict, stale_or_missing_symbols)
        """
        quotes: Dict[str, float] = {}
        market_data: Dict[str, pd.DataFrame] = {}
        stale_or_missing: List[str] = []
        now_dt = datetime.now(timezone.utc)

        for sym in DEFAULT_UNIVERSE:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="1y")
                valid_hist = hist.dropna(subset=["Close"]) if not hist.empty else pd.DataFrame()

                if valid_hist.empty:
                    stale_or_missing.append(f"{sym} (EMPTY_HISTORY)")
                    continue

                market_data[sym] = valid_hist

                # 1. Anchor staleness strictly to the last valid historical bar's date (Reviewer Gap 2)
                last_bar = valid_hist.iloc[-1]
                bar_dt = valid_hist.index[-1].to_pydatetime()
                if bar_dt.tzinfo is None:
                    bar_dt = bar_dt.replace(tzinfo=timezone.utc)

                days_old = (now_dt - bar_dt).days
                if days_old > MAX_PRICE_STALENESS_DAYS:
                    logger.error(f"Stale quote detected for {sym}: Bar date {bar_dt.date()} is {days_old} days old!")
                    stale_or_missing.append(f"{sym} (STALE: {days_old}d old)")
                    continue

                # 2. Use fast_info only as a cross-check for execution price, falling back to bar Close
                last_price = float(last_bar["Close"])
                try:
                    fi_p = getattr(t.fast_info, "last_price", None)
                    if fi_p is not None and not pd.isna(fi_p):
                        fi_val = float(fi_p)
                        if fi_val > 0 and (last_price <= 0 or abs(fi_val - last_price) / last_price <= 0.20):
                            last_price = fi_val
                except Exception:
                    pass

                if last_price <= 0 or pd.isna(last_price):
                    stale_or_missing.append(f"{sym} (INVALID_PRICE: {last_price})")
                else:
                    quotes[sym] = last_price
            except Exception as e:
                logger.error(f"Failed to fetch market data for {sym}: {e}")
                stale_or_missing.append(f"{sym} (ERROR: {str(e)[:30]})")

        return market_data, quotes, stale_or_missing

    def evaluate_rebalance_trigger(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        current_date: datetime,
        duration_scale_changed: bool = False
    ) -> Tuple[bool, str]:
        """
        Evaluates whether a portfolio rebalance is triggered:
        1. Opening allocation (zero positions held)
        2. Duration scale changed by manager
        3. Yearly calendar rebalance (December of a new year)
        4. Drift band trigger: any asset weight drifts > 5 percentage points from target
        """
        if not self.state["positions"]:
            return True, "INITIAL_OPENING_ALLOCATION"

        if duration_scale_changed:
            return True, "MANAGER_DURATION_SCALE_CHANGED"

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

    def run_daily_cycle(
        self,
        quotes: Optional[Dict[str, float]] = None,
        market_data: Optional[Dict[str, pd.DataFrame]] = None,
        max_duration_scale: Optional[float] = None,
        as_of: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Executes daily evaluation, drift monitoring, rebalancing, and state persistence.
        Fails closed on any missing or stale quote.
        """
        # Ingest manager duration scale
        scale_changed = False
        if max_duration_scale is not None:
            old_scale = float(self.state.get("max_duration_scale", 1.0))
            if abs(old_scale - float(max_duration_scale)) > 1e-4:
                scale_changed = True
                self.state["max_duration_scale"] = float(max_duration_scale)
                logger.info(f"Manager max_duration_scale updated: {old_scale:.2f} -> {max_duration_scale:.2f}")

        current_scale = float(self.state.get("max_duration_scale", 1.0))
        portfolio_state = dict(self.state)
        portfolio_state["max_duration_scale"] = current_scale

        stale_symbols: List[str] = []
        if quotes is None or market_data is None:
            fetched_md, fetched_quotes, stale_symbols = self.fetch_market_data()
            if market_data is None:
                market_data = fetched_md
            if quotes is None:
                quotes = fetched_quotes

        target_weights = self.strategy.evaluate_allocations(
            current_date=pd.Timestamp.now(timezone.utc),
            market_data=market_data,
            portfolio_state=portfolio_state
        )
        symbols = list(target_weights.keys())

        # Fail-closed guard: all assets in universe must have valid, fresh quotes
        missing = [sym for sym in symbols if sym not in quotes or quotes[sym] <= 0]
        if missing or stale_symbols:
            logger.error(f"Fail-closed: Missing/stale quotes detected: {missing + stale_symbols}. Aborting cycle without trading.")
            return {
                "status": "FAIL_CLOSED",
                "missing_quotes": missing,
                "stale_quotes": stale_symbols,
                "nav": self.state["nav"]
            }

        now_dt = as_of or datetime.now(timezone.utc)
        today_str = now_dt.strftime("%Y-%m-%d")

        # Accrue daily cash carry on overnight holdings (LIQUIDBEES.NS + uninvested cash)
        # LIQUIDBEES pays yield as daily distributions, keeping price flat at ~INR 1000.
        # Accrues daily cash yield at the protocol repo rate (6.0% repo minus 0.16% TER compounded daily).
        daily_carry_credited = 0.0
        last_carry_date = self.state.get("last_carry_date")
        last_run_ts = self.state.get("last_run_timestamp")

        if last_run_ts is not None and last_carry_date != today_str:
            liquidbees_pos = self.state["positions"].get("LIQUIDBEES.NS", {})
            liquidbees_shares = liquidbees_pos.get("shares", 0)
            liquidbees_px = quotes.get("LIQUIDBEES.NS", liquidbees_pos.get("last_price", 1000.0))

            qualifying_capital = self.state["cash"] + (liquidbees_shares * liquidbees_px)
            if qualifying_capital > 0:
                daily_carry_credited = round(qualifying_capital * DAILY_CARRY_RATE, 2)
                self.state["cash"] = round(self.state["cash"] + daily_carry_credited, 2)
                self.state["total_carry_earned"] = round(self.state.get("total_carry_earned", 0.0) + daily_carry_credited, 2)
                self.state["last_carry_date"] = today_str
                logger.info(f"Credited daily overnight carry: INR {daily_carry_credited:.2f} (Cumulative: INR {self.state['total_carry_earned']:.2f})")

                self.log_trade(
                    symbol="LIQUIDBEES.NS",
                    side="DIVIDEND_CARRY",
                    shares=0,
                    price=round(liquidbees_px, 2),
                    total_cost=-daily_carry_credited,
                    fees=0.0,
                    tax=0.0
                )
        elif last_run_ts is None and last_carry_date is None:
            # First initialization run: anchor carry date without back-crediting
            self.state["last_carry_date"] = today_str

        # Update position prices and calculate holdings value
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
        should_rebal, rebal_reason = self.evaluate_rebalance_trigger(
            current_weights, target_weights, now_dt, duration_scale_changed=scale_changed
        )

        trades_executed = []
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
                        exch = trade_val * (EXCHANGE_FEES_BPS / 10000.0)
                        total_fees = slip + dp + exch

                        # Capital gains tax calculation
                        entry_px = pos.get("entry_price", quotes[sym])
                        gain = (quotes[sym] - entry_px) * sh_to_sell
                        tax = (gain * DEBT_STCG_TAX_RATE) if gain > 0 else 0.0

                        net_proceeds = trade_val - total_fees - tax
                        self.state["cash"] += net_proceeds
                        pos["shares"] -= sh_to_sell

                        self.log_trade(
                            symbol=sym,
                            side="SELL",
                            shares=sh_to_sell,
                            price=quotes[sym],
                            total_cost=-net_proceeds,
                            fees=total_fees,
                            tax=tax
                        )
                        trades_executed.append(f"SELL {sh_to_sell} {sym} @ {quotes[sym]:.2f}")

                        if pos["shares"] <= 0:
                            del self.state["positions"][sym]

            # 2. Buys second with available cash
            for sym, target_w in target_weights.items():
                target_val = total_nav * target_w
                curr_val = self.state["positions"].get(sym, {}).get("shares", 0) * quotes[sym]
                diff = target_val - curr_val

                if diff > 50.0 and quotes[sym] > 0:
                    slip = quotes[sym] * (SLIPPAGE_BPS / 10000.0)
                    stamp = quotes[sym] * (STAMP_DUTY_BUY_BPS / 10000.0)
                    exch = quotes[sym] * (EXCHANGE_FEES_BPS / 10000.0)
                    eff_cost_per_sh = quotes[sym] + slip + stamp + exch

                    sh_to_buy = int(min(diff, self.state["cash"]) // eff_cost_per_sh)
                    if sh_to_buy > 0:
                        trade_val = sh_to_buy * quotes[sym]
                        total_fees = sh_to_buy * (slip + stamp + exch)
                        total_cost = trade_val + total_fees

                        if self.state["cash"] >= total_cost:
                            self.state["cash"] -= total_cost
                            if sym not in self.state["positions"]:
                                self.state["positions"][sym] = {
                                    "shares": sh_to_buy,
                                    "entry_price": quotes[sym],
                                    "entry_date": now_dt.strftime("%Y-%m-%d"),
                                    "last_price": quotes[sym]
                                }
                            else:
                                pos = self.state["positions"][sym]
                                total_sh = pos["shares"] + sh_to_buy
                                pos["entry_price"] = (pos["shares"] * pos["entry_price"] + trade_val) / total_sh
                                pos["shares"] = total_sh
                                pos["last_price"] = quotes[sym]

                            self.log_trade(
                                symbol=sym,
                                side="BUY",
                                shares=sh_to_buy,
                                price=quotes[sym],
                                total_cost=total_cost,
                                fees=total_fees,
                                tax=0.0
                            )
                            trades_executed.append(f"BUY {sh_to_buy} {sym} @ {quotes[sym]:.2f}")

            self.state["last_rebalance_date"] = now_dt.isoformat()

        # Update and persist equity log & state
        self.log_equity(quotes)
        self._save_state()

        return {
            "status": "SUCCESS",
            "rebalance_executed": should_rebal,
            "rebalance_reason": rebal_reason if should_rebal else None,
            "trades": trades_executed,
            "nav": self.state["nav"],
            "cash": self.state["cash"],
            "daily_carry_credited": daily_carry_credited,
            "total_carry_earned": self.state.get("total_carry_earned", 0.0),
            "positions": {s: p["shares"] for s, p in self.state["positions"].items()},
            "target_weights": target_weights,
            "max_duration_scale": current_scale,
            "drawdown_pct": self.state["current_drawdown_pct"]
        }
