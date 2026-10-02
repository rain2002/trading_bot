from trading_system.app.common.interfaces import PositionSizer

class BasicPositionSizer(PositionSizer):
    def calculate_size(self, signal: int, risk_parameters: any, capital: float) -> float:
        """
        Naive sizing: Buy or sell 10 shares flat.
        In the future, this will scale dynamically based on ML confidence scores and Prop Firm Risk remaining.
        """
        return 10.0 if signal == 1 else -10.0
