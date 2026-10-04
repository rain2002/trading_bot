from abc import ABC, abstractmethod
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
    def evaluate_trade(self, trade_request: Any, portfolio_state: Any) -> bool:
        """Return True if the trade passes all risk and exposure limits, else False."""
        pass

class PositionSizer(ABC):
    @abstractmethod
    def calculate_size(self, signal: Any, risk_parameters: Any, capital: float) -> float:
        """Determine position size based on signal confidence and risk parameters."""
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

class ReconciliationService(ABC):
    @abstractmethod
    def reconcile(self, internal_state: Any, broker_state: Any) -> bool:
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
