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

    def calculate_transaction_costs(self, trade_value: float, shares: float, side: str = "BUY") -> float:
        """
        Computes accurate total transaction friction (slippage + brokerage + exchange turnover fee + GST + STT/taxes).
        """
        trade_value = abs(trade_value)
        shares = abs(shares)
        side_norm = side.strip().upper()

        # 1. Slippage (e.g. 5 bps = 0.05%)
        slippage = trade_value * (self.slippage_bps / 10000.0)

        # 2. Brokerage / Commission
        comm = self.commission_flat
        if self.commission_per_share > 0:
            comm += shares * self.commission_per_share
        if self.commission_bps > 0:
            comm += trade_value * (self.commission_bps / 10000.0)

        # 3. Exchange Turnover / Regulatory Fees
        exchange_fee = 0.0
        if self.exchange_turnover_bps > 0:
            exchange_fee = trade_value * (self.exchange_turnover_bps / 10000.0)

        sec_fee = 0.0
        if self.sec_finra_fee_bps > 0 and side_norm == "SELL":
            sec_fee = trade_value * (self.sec_finra_fee_bps / 10000.0)

        # 4. GST / VAT on Brokerage and Exchange Fees (e.g., 18% in India)
        gst_tax = 0.0
        if self.gst_pct_on_brokerage > 0:
            gst_tax = (comm + exchange_fee) * self.gst_pct_on_brokerage

        # 5. Transaction Taxes (STT, Stamp Duty)
        taxes = 0.0
        if self.market_code == "IN":
            # In India: STT applies to both BUY & SELL on delivery (0.1%)
            if self.tax_rate_stt > 0:
                taxes += trade_value * self.tax_rate_stt
            # Stamp Duty in India applies to BUY only (1.5 bps = 0.015%)
            if self.stamp_duty_bps > 0 and side_norm == "BUY":
                taxes += trade_value * (self.stamp_duty_bps / 10000.0)
        else:
            if self.tax_rate_stt > 0:
                taxes += trade_value * self.tax_rate_stt

        total_friction = slippage + comm + exchange_fee + sec_fee + gst_tax + taxes
        return round(total_friction, 4)
