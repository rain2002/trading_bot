import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class MarketConfig:
    market_code: str
    country: str
    name: str
    benchmark_symbol: str
    benchmark_name: str
    currency_symbol: str
    currency_code: str
    broker_adapter: str
    supports_fractional: bool
    integer_shares_only: bool
    universe_file: str
    trading_timezone: str
    open_time: str
    close_time: str
    slippage_bps: float = 5.0
    commission_per_share: float = 0.0
    commission_flat: float = 0.0
    commission_bps: float = 0.0
    tax_rate_stt: float = 0.0
    exchange_turnover_bps: float = 0.0
    gst_pct_on_brokerage: float = 0.0
    stamp_duty_bps: float = 0.0
    sec_finra_fee_bps: float = 0.0
    # Statutory Indian Delivery Fee Schedule (Dhan / NSE)
    brokerage_delivery_flat: float = 0.0
    dp_charge_per_sale: float = 0.0
    tax_rate_stt_buy: float = 0.0
    tax_rate_stt_sell: float = 0.0
    stamp_duty_buy: float = 0.0
    exchange_turnover_rate: float = 0.0
    sebi_turnover_rate: float = 0.0
    gst_rate: float = 0.18
    cost_floor_max_pct: float = 0.15
    max_holdings: int = 10
    target_position_weight: float = 0.10
    max_single_stock: float = 0.12
    dynamic_cap_max: float = 0.25
    min_position_pct: float = 0.04
    hard_stop_loss_pct: float = -0.08
    breakeven_gain_trigger_pct: float = 0.12
    breakeven_locked_profit_pct: float = 0.02
    runner_gain_trigger_pct: float = 0.30
    runner_max_drawdown_from_peak_pct: float = 0.14
    raw_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def get_markets_dir(cls) -> str:
        return os.path.join(os.path.dirname(__file__), "markets")

    @classmethod
    def list_available_markets(cls) -> List[str]:
        m_dir = cls.get_markets_dir()
        if not os.path.exists(m_dir):
            return []
        return [f.replace(".json", "").upper() for f in os.listdir(m_dir) if f.endswith(".json")]

    @classmethod
    def load(cls, identifier: str = "US") -> "MarketConfig":
        """
        Loads market configuration by code ('US', 'IN') or country name.
        """
        ident = identifier.strip().lower()
        alias_map = {
            "us": "us.json",
            "usa": "us.json",
            "united states": "us.json",
            "in": "india.json",
            "india": "india.json",
            "nse": "india.json"
        }
        filename = alias_map.get(ident, f"{ident}.json")
        m_dir = cls.get_markets_dir()
        filepath = os.path.join(m_dir, filename)

        if not os.path.exists(filepath):
            # Fallback check direct path
            if os.path.exists(identifier):
                filepath = identifier
            else:
                available = cls.list_available_markets()
                raise FileNotFoundError(
                    f"Market config '{identifier}' not found at {filepath}. Available markets: {available}"
                )

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        bm = data.get("benchmark", {})
        curr = data.get("currency", {})
        brk = data.get("broker", {})
        univ = data.get("universe", {})
        hrs = data.get("trading_hours", {})
        costs = data.get("costs", {})
        rules = data.get("portfolio_rules", {})

        return cls(
            market_code=data.get("market_code", "US").upper(),
            country=data.get("country", "Unknown"),
            name=data.get("name", "Equity Market"),
            benchmark_symbol=bm.get("symbol", "SPY"),
            benchmark_name=bm.get("name", "Benchmark Index"),
            currency_symbol=curr.get("symbol", "$"),
            currency_code=curr.get("code", "USD"),
            broker_adapter=brk.get("adapter", "alpaca"),
            supports_fractional=bool(brk.get("supports_fractional", True)),
            integer_shares_only=bool(brk.get("integer_shares_only", False)),
            universe_file=univ.get("file", ""),
            trading_timezone=hrs.get("timezone", "America/New_York"),
            open_time=hrs.get("open", "09:30"),
            close_time=hrs.get("close", "16:00"),
            slippage_bps=float(costs.get("slippage_bps", 5.0)),
            commission_per_share=float(costs.get("commission_per_share", 0.0)),
            commission_flat=float(costs.get("commission_flat", 0.0)),
            commission_bps=float(costs.get("commission_bps", 0.0)),
            tax_rate_stt=float(costs.get("tax_rate_stt", 0.0)),
            exchange_turnover_bps=float(costs.get("exchange_turnover_bps", 0.0)),
            gst_pct_on_brokerage=float(costs.get("gst_pct_on_brokerage", 0.0)),
            stamp_duty_bps=float(costs.get("stamp_duty_bps", 0.0)),
            sec_finra_fee_bps=float(costs.get("sec_finra_fee_bps", 0.0)),
            # Statutory Indian Costs
            brokerage_delivery_flat=float(costs.get("brokerage_delivery_flat", costs.get("commission_flat", 0.0))),
            dp_charge_per_sale=float(costs.get("dp_charge_per_sale", 15.34 if data.get("market_code") == "IN" else 0.0)),
            tax_rate_stt_buy=float(costs.get("tax_rate_stt_buy", costs.get("tax_rate_stt", 0.001 if data.get("market_code") == "IN" else 0.0))),
            tax_rate_stt_sell=float(costs.get("tax_rate_stt_sell", costs.get("tax_rate_stt", 0.001 if data.get("market_code") == "IN" else 0.0))),
            stamp_duty_buy=float(costs.get("stamp_duty_buy", (costs.get("stamp_duty_bps", 1.5) / 10000.0) if data.get("market_code") == "IN" else 0.0)),
            exchange_turnover_rate=float(costs.get("exchange_turnover_rate", (costs.get("exchange_turnover_bps", 0.345) / 10000.0) if data.get("market_code") == "IN" else 0.0)),
            sebi_turnover_rate=float(costs.get("sebi_turnover_rate", 0.000001 if data.get("market_code") == "IN" else 0.0)),
            gst_rate=float(costs.get("gst_rate", costs.get("gst_pct_on_brokerage", 0.18))),
            cost_floor_max_pct=float(rules.get("cost_floor_max_pct", 0.15)),
            max_holdings=int(rules.get("max_holdings", 10)),
            target_position_weight=float(rules.get("target_position_weight", 0.10)),
            max_single_stock=float(rules.get("max_single_stock", 0.12)),
            dynamic_cap_max=float(rules.get("dynamic_cap_max", 0.25)),
            min_position_pct=float(rules.get("min_position_pct", 0.04)),
            hard_stop_loss_pct=float(rules.get("hard_stop_loss_pct", -0.08)),
            breakeven_gain_trigger_pct=float(rules.get("breakeven_gain_trigger_pct", 0.12)),
            breakeven_locked_profit_pct=float(rules.get("breakeven_locked_profit_pct", 0.02)),
            runner_gain_trigger_pct=float(rules.get("runner_gain_trigger_pct", 0.30)),
            runner_max_drawdown_from_peak_pct=float(rules.get("runner_max_drawdown_from_peak_pct", 0.14)),
            raw_config=data
        )

    def get_universe(self, project_root: Optional[str] = None) -> List[str]:
        """
        Loads the list of tradeable constituent tickers for this market.
        Preserves exchange dot suffixes (.NS, .L, .T) for international markets.
        Only swaps '.' to '-' for US dual-class tickers (e.g., BRK.B -> BRK-B).
        Appends ticker_suffix if configured and absent (e.g. for NSE midcap CSV).
        """
        if not self.universe_file:
            return []

        if project_root is None:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

        target_path = os.path.join(project_root, self.universe_file)
        if not os.path.exists(target_path):
            # Check relative to repo root
            target_path = os.path.abspath(self.universe_file)
            if not os.path.exists(target_path):
                return []

        ticker_suffix = self.raw_config.get("universe", {}).get("ticker_suffix", "")

        tickers = []
        if target_path.endswith(".txt"):
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if raw and not raw.startswith("#"):
                        # Only US dual-class tickers like BRK.B use hyphens in Yahoo Finance
                        if self.market_code == "US":
                            item = raw.replace(".", "-")
                        else:
                            item = raw
                        if ticker_suffix and not item.endswith(ticker_suffix) and "." not in item:
                            item = f"{item}{ticker_suffix}"
                        tickers.append(item)
        elif target_path.endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(target_path)
            col = self.raw_config.get("universe", {}).get("column", "Symbol")
            if col in df.columns:
                for x in df[col]:
                    raw = str(x).strip()
                    if raw and raw.lower() != "nan":
                        if self.market_code == "US":
                            item = raw.replace(".", "-")
                        else:
                            item = raw
                        if ticker_suffix and not item.endswith(ticker_suffix) and "." not in item:
                            item = f"{item}{ticker_suffix}"
                        tickers.append(item)

        return tickers

    def calculate_transaction_costs(
        self,
        trade_value: float,
        shares: float = 0.0,
        side: str = "BUY",
        return_breakdown: bool = False
    ) -> Any:
        """
        Computes accurate total transaction friction:
        - Delivery Brokerage
        - Statutory Taxes (STT, Stamp Duty)
        - Exchange Turnover Fee & SEBI Turnover Fee
        - Depository Participant (DP) Fee (flat ₹15.34 on SELL only)
        - GST on taxable services (Brokerage + Exchange + SEBI + DP Fee)
        - Execution Slippage (e.g. 5 bps)
        """
        trade_value = abs(float(trade_value))
        shares = abs(float(shares))
        side_norm = side.strip().upper()

        if self.market_code == "IN":
            brokerage = self.brokerage_delivery_flat

            # STT: 0.1% on Buy value AND 0.1% on Sell value (Delivery)
            stt_rate = self.tax_rate_stt_buy if side_norm == "BUY" else self.tax_rate_stt_sell
            stt = trade_value * stt_rate

            # Stamp Duty: 0.015% on Buy value only
            stamp_duty = (trade_value * self.stamp_duty_buy) if side_norm == "BUY" else 0.0

            # Exchange Turnover Fee: 0.00345% on Buy and Sell value
            exchange_fee = trade_value * self.exchange_turnover_rate

            # SEBI Turnover Fee: 0.0001% (₹10 per crore) on Buy and Sell
            sebi_fee = trade_value * self.sebi_turnover_rate

            # DP Charge: Flat ₹15.34 deducted ONLY on sell transactions, per scrip, per day
            dp_fee = self.dp_charge_per_sale if side_norm == "SELL" else 0.0

            # GST: 18% on (Brokerage + Exchange Fee + SEBI Fee + DP Fee)
            taxable_services = brokerage + exchange_fee + sebi_fee + dp_fee
            gst = taxable_services * self.gst_rate

            # Execution Slippage (5 bps default)
            slippage = trade_value * (self.slippage_bps / 10000.0)

            statutory_total = brokerage + stt + stamp_duty + exchange_fee + sebi_fee + dp_fee + gst
            total_friction = statutory_total + slippage

            if return_breakdown:
                return {
                    "trade_value": trade_value,
                    "side": side_norm,
                    "brokerage": round(brokerage, 4),
                    "stt": round(stt, 4),
                    "stamp_duty": round(stamp_duty, 4),
                    "exchange_fee": round(exchange_fee, 4),
                    "sebi_fee": round(sebi_fee, 4),
                    "dp_charge": round(dp_fee, 4),
                    "gst": round(gst, 4),
                    "statutory_total": round(statutory_total, 4),
                    "slippage": round(slippage, 4),
                    "total": round(total_friction, 4),
                }
            return round(total_friction, 4)
        else:
            # US / other markets
            slippage = trade_value * (self.slippage_bps / 10000.0)
            comm = self.commission_flat
            if self.commission_per_share > 0:
                comm += shares * self.commission_per_share
            if self.commission_bps > 0:
                comm += trade_value * (self.commission_bps / 10000.0)

            sec_fee = (trade_value * (self.sec_finra_fee_bps / 10000.0)) if side_norm == "SELL" else 0.0
            total_friction = slippage + comm + sec_fee

            if return_breakdown:
                return {
                    "trade_value": trade_value,
                    "side": side_norm,
                    "brokerage": round(comm, 4),
                    "sec_fee": round(sec_fee, 4),
                    "slippage": round(slippage, 4),
                    "total": round(total_friction, 4),
                }
            return round(total_friction, 4)

    def validate_cost_floor_gate(
        self,
        estimated_round_trip_costs: float,
        expected_trade_profit: float,
        max_cost_pct: float = 0.15
    ) -> bool:
        """
        15% Cost Floor Gate:
        Rejects trade if total estimated round-trip costs exceed 15% of expected trade profit.
        """
        if expected_trade_profit <= 0:
            return False
        return estimated_round_trip_costs <= (max_cost_pct * expected_trade_profit)
