from typing import Any, Optional
from trading_system.app.common.interfaces import RiskEngine


class BasicRiskEngine(RiskEngine):
    """
    Dollar-exposure risk engine.

    Configured with two limits:
    - max_position_pct: maximum single-stock exposure as a fraction of portfolio (default 15%)
    - max_portfolio_pct: maximum total invested exposure as a fraction of portfolio (default 95%)

    evaluate_trade() receives:
      trade_request: dict with keys 'symbol', 'quantity', 'price_hint'
      portfolio_state: dict of {symbol: current_qty}
      total_equity: float — current portfolio value in dollars
      current_invested_value: Optional[float] — exact total dollar value invested across holdings
    """

    def __init__(
        self,
        max_position_pct: float = 0.15,   # 15% max per single stock
        max_portfolio_pct: float = 0.95,  # 95% max total invested
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_pct = max_portfolio_pct

    def evaluate_trade(
        self,
        trade_request: Any,
        portfolio_state: Any,
        total_equity: float = 100_000.0,
        current_invested_value: Optional[float] = None,
    ) -> bool:
        """
        Rejects a trade if it would push any single position above max_position_pct
        of portfolio equity. Skips evaluation for pure SELL orders (reducing exposure
        is always safe from a risk perspective).
        """
        symbol = trade_request.get("symbol")
        proposed_quantity = trade_request.get("quantity", 0)
        price_hint = trade_request.get("price_hint", 0.0)

        current_qty = portfolio_state.get(symbol, 0.0)
        
        # Sells: allow closing/reducing long positions, but block unvetted short sales
        if proposed_quantity < 0:
            if current_qty + proposed_quantity < -1e-6:
                print(f"   [RISK BLOCK] {symbol}: Short selling not permitted in long-only mode.")
                return False
            return True

        # Buy orders require valid price hint for exposure calculation
        if price_hint <= 0:
            print(f"   [RISK BLOCK] {symbol}: Cannot vet trade without valid price_hint ({price_hint}).")
            return False

        # 1. Single-stock position limit
        new_qty = current_qty + proposed_quantity
        new_dollar_exposure = abs(new_qty) * price_hint
        max_dollar_allowed = total_equity * self.max_position_pct

        if new_dollar_exposure > max_dollar_allowed:
            print(
                f"   [RISK BLOCK] {symbol}: proposed exposure ${new_dollar_exposure:,.0f} "
                f"> max allowed ${max_dollar_allowed:,.0f} "
                f"({self.max_position_pct*100:.0f}% of ${total_equity:,.0f})"
            )
            return False

        # 2. Total portfolio exposure limit
        if current_invested_value is not None:
            total_current_exposure = current_invested_value + (proposed_quantity * price_hint)
        else:
            total_current_exposure = sum(
                abs(qty) * price_hint for sym, qty in portfolio_state.items() if sym != symbol
            ) + new_dollar_exposure
        max_portfolio_dollar = total_equity * self.max_portfolio_pct

        if total_current_exposure > max_portfolio_dollar:
            print(
                f"   [RISK BLOCK] {symbol}: Total portfolio exposure ${total_current_exposure:,.0f} "
                f"exceeds ceiling ${max_portfolio_dollar:,.0f} ({self.max_portfolio_pct*100:.0f}%)"
            )
            return False

        return True
