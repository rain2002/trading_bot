from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd
from datetime import datetime

class PointInTimeDataProvider(ABC):
    @abstractmethod
    def get_data_as_of(self, symbol: str, current_time: datetime) -> pd.DataFrame:
        """
        Query the data store: "What exact information was actually known at current_time?"
        This prevents future data leakage and ensures corporate actions are handled correctly.
        """
        pass

class Dataset(ABC):
    @abstractmethod
    def get_data(self) -> pd.DataFrame:
        pass
        
    @abstractmethod
    def get_version(self) -> str:
        """Return the immutable version of this dataset for reproducibility."""
        pass

class Strategy(ABC):
    @abstractmethod
    def generate_signals(self, point_in_time_data: Any) -> Dict[str, Any]:
        """Generate trading signals strictly based on point-in-time data."""
        pass

    def generate_signal(self, point_in_time_data: Any) -> Any:
        """Single-asset compatibility hook."""
        return self.generate_signals(point_in_time_data)

class StrategyInterface(ABC):
    """
    Standardized Strategy Interface for the Multi-Bot Trading System.
    Each specialist bot (ETF Bot, S&P 500 Bot, NSE Bot) implements this contract.
    """
    @abstractmethod
    def evaluate_allocations(
        self,
        current_date: pd.Timestamp,
        market_data: Dict[str, pd.DataFrame],
        portfolio_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Evaluate market data as of current_date and output target asset weights (0.0 to 1.0).
        Sum of weights must be <= 1.0. Unallocated weight defaults to cash/bonds sleeve.
        """
        pass

    @abstractmethod
    def get_risk_status(self) -> Dict[str, Any]:
        """
        Returns strategy-specific risk metrics (current drawdown, trend states, defensive flags).
        """
        pass


@dataclass
class BotReport:
    nav: float            # bot NAV in INR, from its own state
    risk_status: Dict[str, Any]
    gate_status: str      # NONE, GATE_A, GATE_B_PAPER, LIVE_APPROVED
    last_update: pd.Timestamp
    stale: bool           # True if older than one NSE trading day


class ManagerInterface(ABC):
    """
    Standardized Manager Interface for the Multi-Bot Trading System.
    Governs capital allocation across bots, portfolio-level drawdown throttling,
    and kill-switch enforcement.
    """
    @abstractmethod
    def evaluate_shares(
        self,
        as_of: pd.Timestamp,
        reports: Dict[str, BotReport],
        nav_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """Target capital share per bot plus the cash sleeve, summing to 1.0.
        A bot whose gate_status is below LIVE_APPROVED gets 0.0 real share.
        A stale report freezes that bot's share and raises an alert."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Throttle level, drawdown, halted flag, last reconciliation gap."""
        pass

class Portfolio(ABC):
    @abstractmethod
    def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """Update internal portfolio state after an execution."""
        pass
        
    @abstractmethod
    def get_target_weights(self) -> Dict[str, float]:
        """Calculate the target allocation weights."""
        pass

class RiskEngine(ABC):
    @abstractmethod
    def evaluate_trade(self, trade_request: Any, portfolio_state: Any, total_equity: float = 100000.0) -> bool:
        """Return True if the trade passes all risk and exposure limits, else False."""
        pass

class PositionSizer(ABC):
    @abstractmethod
    def calculate_size(self, signal: Any, risk_parameters: Any, capital: float) -> float:
        """Determine position size based on signal confidence and risk parameters."""
        pass

class BrokerAPIError(RuntimeError):
    """Base exception for broker communication or execution failures."""
    pass


class BrokerConnectionError(BrokerAPIError):
    """Raised when broker API connection fails, disconnects, times out, or fails auth."""
    pass


class OrderExecutionError(BrokerAPIError):
    """Raised when order submission, validation, or modification fails on the broker."""
    pass


class ExecutionAdapter(ABC):
    @abstractmethod
    def submit_order(self, order: Any) -> Any:
        """Submit an order to the execution layer (paper or live)."""
        pass

class BrokerAdapter(ABC):
    @abstractmethod
    def get_positions(self) -> Dict[str, float]:
        """Fetch true positions from the broker."""
        pass
        
    @abstractmethod
    def get_order_status(self, order_id: str) -> str:
        """Fetch true order status from the broker."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if broker API connection is currently active and responsive."""
        pass

    @abstractmethod
    def get_positions_detailed(self) -> List[Dict[str, Any]]:
        """Fetch detailed positions including entry price, current price, and unrealized PnL."""
        pass

    @abstractmethod
    def get_account_details(self) -> Dict[str, Any]:
        """Fetch comprehensive account metrics."""
        pass

    @abstractmethod
    def get_account_equity(self) -> float:
        """Fetch total portfolio equity."""
        pass

class ReconciliationService(ABC):
    @abstractmethod
    def reconcile(self, internal_state: Any = None, broker_state: Any = None) -> bool:
        """Compare internal positions/orders against broker state and halt if mismatched."""
        pass

class PerformanceAnalyzer(ABC):
    @abstractmethod
    def calculate_metrics(self, trade_history: List[Any], equity_curve: pd.Series) -> Dict[str, float]:
        """Calculate statistical robustness metrics like Sharpe, Max Drawdown, Calmar, etc."""
        pass

class AlertService(ABC):
    @abstractmethod
    def send_alert(self, level: str, message: str) -> None:
        """Dispatch alerts (e.g. kill switch events) to the monitoring dashboard or operator."""
        pass
