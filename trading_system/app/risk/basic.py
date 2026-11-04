from typing import Any, Optional, Dict
from trading_system.app.common.interfaces import RiskEngine


class ImmutableRiskViolationError(ValueError):
    """Raised when an algorithm, user config, or optimizer attempts to loosen immutable risk limits."""
    pass


# ==============================================================================
# Institutional Immutable Risk Constants
# ==============================================================================
HARD_STOP_LOSS_PCT: float = -0.08        # -8% maximum hard stop loss floor
CRO_MAX_DRAWDOWN_PCT: float = -0.18      # -18% fund-level maximum drawdown ceiling
MAX_POSITIONS_CEILING: int = 10          # 10 maximum concurrent holdings
LONG_ONLY_MANDATE: bool = True           # Strictly long-only cash equities


def validate_risk_config(config: Dict[str, Any]) -> bool:
    """
    Validates a loaded market/risk config against the fund's immutable code-level constants.
    Raises ImmutableRiskViolationError if any limit is loosened.
    """
    # 1. Hard stop loss check
    stop_key = None
    for k in ["hard_stop", "hard_stop_loss_pct", "global_default_pct"]:
        if k in config:
            stop_key = k
            break
    if stop_key:
        stop = float(config[stop_key])
        if stop < HARD_STOP_LOSS_PCT:
            raise ImmutableRiskViolationError(
                f"Immutable Risk Breach: Configured stop loss {stop} is looser than immutable ceiling {HARD_STOP_LOSS_PCT}."
            )

    # 2. Max concurrent positions ceiling check
    pos_key = None
    for k in ["max_positions", "max_holdings"]:
        if k in config:
            pos_key = k
            break
    if pos_key:
        max_pos = int(config[pos_key])
        if max_pos > MAX_POSITIONS_CEILING:
            raise ImmutableRiskViolationError(
                f"Immutable Risk Breach: max_positions ({max_pos}) exceeds fund ceiling ({MAX_POSITIONS_CEILING})."
            )

    # 3. Long-only mandate check
    if config.get("allow_shorting", False) or config.get("short_selling_enabled", False):
        raise ImmutableRiskViolationError(
            "Immutable Risk Breach: Short selling is strictly prohibited under the fund's Long-Only Mandate."
        )

    # 4. Max drawdown check
    dd_key = None
    for k in ["max_drawdown", "cro_max_drawdown_pct"]:
        if k in config:
            dd_key = k
            break
    if dd_key:
        dd = float(config[dd_key])
        if dd < CRO_MAX_DRAWDOWN_PCT:
            raise ImmutableRiskViolationError(
                f"Immutable Risk Breach: Max drawdown limit {dd} is looser than immutable floor {CRO_MAX_DRAWDOWN_PCT}."
            )

    return True


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
        max_position_pct: float = 0.30,   # Dynamic ceiling: 15% default, up to 30% for high conviction / low candidate count
        max_portfolio_pct: float = 0.95,  # 95% max total invested
        **kwargs
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_pct = max_portfolio_pct
        if kwargs.get("config"):
            validate_risk_config(kwargs["config"])

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
        proposed_quantity = trade_request.get("quantity", trade_request.get("shares", 0))
        price_hint = trade_request.get("price_hint", trade_request.get("price", 0.0))

        if isinstance(portfolio_state, dict) and "positions" in portfolio_state and isinstance(portfolio_state["positions"], dict):
            positions_map = portfolio_state["positions"]
        elif isinstance(portfolio_state, dict):
            positions_map = portfolio_state
        else:
            positions_map = {}

        current_qty = positions_map.get(symbol, 0.0)
        if isinstance(current_qty, dict):
            current_qty = current_qty.get("qty", 0.0)
        
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
            # Fallback estimation when exact invested value is not provided
            total_other_exposure = 0.0
            for sym, val in positions_map.items():
                if sym in (symbol, "cash", "total_equity", "equity", "available_funds", "buying_power"):
                    continue
                if isinstance(val, dict):
                    mv = val.get("market_value") or (abs(float(val.get("qty", 0))) * float(val.get("price", 0)))
                    total_other_exposure += abs(float(mv))
                elif isinstance(val, (int, float)):
                    total_other_exposure += abs(float(val)) * price_hint
            total_current_exposure = total_other_exposure + new_dollar_exposure
        max_portfolio_dollar = total_equity * self.max_portfolio_pct

        if total_current_exposure > max_portfolio_dollar:
            print(
                f"   [RISK BLOCK] {symbol}: Total portfolio exposure ${total_current_exposure:,.0f} "
                f"exceeds ceiling ${max_portfolio_dollar:,.0f} ({self.max_portfolio_pct*100:.0f}%)"
            )
            return False

        # 3. Cost Floor Gate (reject trade if estimated friction exceeds 15% of expected profit)
        expected_profit = trade_request.get("expected_profit")
        estimated_friction = trade_request.get("estimated_friction")
        if expected_profit is not None and estimated_friction is not None:
            if float(expected_profit) > 0 and float(estimated_friction) > 0.15 * float(expected_profit):
                print(
                    f"   [RISK BLOCK - COST FLOOR GATE] {symbol}: Estimated friction {estimated_friction:.2f} "
                    f"exceeds 15% of expected trade profit {expected_profit:.2f}."
                )
                return False

        return True
