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
        Loads market configuration by code ('US', 'IN', 'UK', 'JP') or country name.
        """
        ident = identifier.strip().lower()
        alias_map = {
            "us": "us.json",
            "usa": "us.json",
            "united states": "us.json",
            "in": "india.json",
            "india": "india.json",
            "nse": "india.json",
            "uk": "uk.json",
            "united kingdom": "uk.json",
            "ftse": "uk.json",
            "jp": "japan.json",
            "japan": "japan.json",
            "nikkei": "japan.json",
            "tse": "japan.json"
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

        tickers = []
        if target_path.endswith(".txt"):
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    item = line.strip().replace(".", "-")
                    if item and not item.startswith("#"):
                        tickers.append(item)
        elif target_path.endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(target_path)
            col = self.raw_config.get("universe", {}).get("column", "Symbol")
            if col in df.columns:
                tickers = [str(x).strip() for x in df[col] if str(x).strip()]

        return tickers

    def calculate_transaction_costs(self, trade_value: float, shares: float, side: str = "BUY") -> float:
        """
        Computes accurate total transaction friction (slippage + brokerage + STT/taxes).
        """
        trade_value = abs(trade_value)
        shares = abs(shares)

        # 1. Slippage (e.g. 5 bps = 0.05%)
        slippage = trade_value * (self.slippage_bps / 10000.0)

        # 2. Brokerage / Commission
        comm = self.commission_flat
        if self.commission_per_share > 0:
            comm += shares * self.commission_per_share
        if self.commission_bps > 0:
            comm += trade_value * (self.commission_bps / 10000.0)

        # 3. Transaction Taxes (e.g. STT in India, Stamp Duty in UK)
        taxes = 0.0
        if self.tax_rate_stt > 0:
            # In UK, Stamp Duty (0.5%) applies to BUY only; In India STT applies on delivery buy/sell
            if self.market_code == "UK":
                if side.upper() == "BUY":
                    taxes = trade_value * self.tax_rate_stt
            else:
                taxes = trade_value * self.tax_rate_stt

        return round(slippage + comm + taxes, 4)
