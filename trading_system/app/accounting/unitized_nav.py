"""
Unitized NAV & Tactical SIP Deployment Engine (Option B - Dip-Buffer Model)
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 2, Item 4)

Fiduciary Principles:
1. Unitized NAV Accounting: Implements Net Asset Value (NAV) unit accounting identical
   to an institutional mutual fund or hedge fund.
   - Deposits (lump sums or recurring SIPs) issue new units at current NAV.
   - Inflows are recorded as capital contributions and NEVER falsely counted as trading profit.
   - Eliminates false return inflation and Sharpe distortion from incoming savings.
2. Tactical Cash Reserve Buffer:
   - Incoming SIP cash is parked in the Tactical Liquid Reserve rather than FOMO-chasing all-time highs.
   - Dry powder is opportunistically deployed on high-quality pullbacks (RSI < 35, Lower Bollinger Band).
3. 30-Day Tactical Drip Feeder:
   - If market runs in extended bull market without pullbacks for 30 consecutive days,
     gradually drips unspent tactical cash into top-ranked momentum compounders.
"""

import os
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from trading_system.app.common.logger import get_logger

logger = get_logger("UnitizedNAV")


class UnitizedNAVEngine:
    """
    Institutional Net Asset Value (NAV) and Tactical SIP Capital Management Engine.
    """

    INITIAL_NAV_PER_UNIT: float = 100.0  # Base unit valuation ($100 or ₹100 per unit)
    DRIP_FEEDER_TRIGGER_DAYS: int = 30    # 30-day runaway bull market drip feeder

    def __init__(
        self,
        ledger_path: Optional[str] = None,
        initial_capital: float = 100000.0
    ):
        if ledger_path is None:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ledger_path = os.path.join(root_dir, "data", "unitized_nav_ledger.json")
        self.ledger_path = os.path.abspath(ledger_path)
        self.initial_capital = float(initial_capital)
        self._load_ledger()

    def _load_ledger(self):
        """Loads unitized accounting ledger from disk or creates initial state."""
        self.state: Dict[str, Any] = {
            "base_nav_per_unit": self.INITIAL_NAV_PER_UNIT,
            "nav_per_unit": self.INITIAL_NAV_PER_UNIT,
            "total_units": self.initial_capital / self.INITIAL_NAV_PER_UNIT,
            "total_portfolio_value": self.initial_capital,
            "cumulative_deposits": self.initial_capital,
            "cumulative_withdrawals": 0.0,
            "tactical_cash_reserve": 0.0,
            "last_dip_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "transactions": []
        }

        if os.path.isfile(self.ledger_path):
            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state.update(data)
            except Exception as e:
                logger.warning(f"Could not load unitized NAV ledger: {e}. Starting fresh.")
        else:
            # Seed initial deposit transaction
            self.state["transactions"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "INITIAL_SEED",
                "amount": self.initial_capital,
                "nav_per_unit": self.INITIAL_NAV_PER_UNIT,
                "units_issued": self.state["total_units"],
                "total_units_after": self.state["total_units"],
                "portfolio_value_after": self.initial_capital
            })
            self._save_ledger()

    def _save_ledger(self):
        """Persists unitized accounting ledger to disk."""
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save unitized NAV ledger: {e}")

    def update_portfolio_valuation(self, current_total_value: float, timestamp: Optional[datetime] = None) -> float:
        """
        Updates portfolio valuation and calculates true NAV per unit:
        NAV per unit = Total Portfolio Value / Units Outstanding.
        """
        now = timestamp or datetime.now(timezone.utc)
        current_total_value = max(0.0, float(current_total_value))
        units = max(1e-6, float(self.state.get("total_units", 1.0)))

        nav_per_unit = current_total_value / units
        self.state["total_portfolio_value"] = round(current_total_value, 2)
        self.state["nav_per_unit"] = round(nav_per_unit, 4)

        self._save_ledger()
        return self.state["nav_per_unit"]

    def process_deposit(
        self,
        deposit_amount: float,
        portfolio_value_before_deposit: float,
        timestamp: Optional[datetime] = None,
        allocate_to_tactical_reserve: bool = True
    ) -> Dict[str, Any]:
        """
        Processes capital inflow (lump sum or SIP):
        1. Computes NAV per unit BEFORE deposit:
           NAV = portfolio_value_before_deposit / existing_units.
        2. Issues new units: units_issued = deposit_amount / NAV.
        3. Updates total portfolio value: portfolio_value_after = portfolio_value_before + deposit_amount.
        4. NAV per unit remains completely UNCHANGED by deposit!
        5. Deposits cash into Tactical Cash Reserve Buffer.
        """
        now = timestamp or datetime.now(timezone.utc)
        deposit_amount = float(deposit_amount)
        if deposit_amount <= 0:
            raise ValueError(f"Deposit amount must be positive, got {deposit_amount}")

        existing_units = max(1e-6, float(self.state.get("total_units", 1.0)))
        
        # Calculate pre-deposit NAV per unit
        if portfolio_value_before_deposit <= 0:
            nav_before = float(self.state.get("nav_per_unit", self.INITIAL_NAV_PER_UNIT))
        else:
            nav_before = portfolio_value_before_deposit / existing_units

        # Issue units at current NAV
        new_units_issued = deposit_amount / nav_before
        total_units_after = existing_units + new_units_issued
        total_value_after = portfolio_value_before_deposit + deposit_amount

        # Update state
        self.state["total_units"] = round(total_units_after, 6)
        self.state["total_portfolio_value"] = round(total_value_after, 2)
        self.state["nav_per_unit"] = round(nav_before, 4)  # INVARIANT: NAV per unit does not change on deposit!
        self.state["cumulative_deposits"] = round(float(self.state.get("cumulative_deposits", 0.0)) + deposit_amount, 2)

        if allocate_to_tactical_reserve:
            self.state["tactical_cash_reserve"] = round(float(self.state.get("tactical_cash_reserve", 0.0)) + deposit_amount, 2)

        tx_record = {
            "timestamp": now.isoformat(),
            "type": "DEPOSIT",
            "deposit_amount": deposit_amount,
            "nav_per_unit": round(nav_before, 4),
            "units_issued": round(new_units_issued, 6),
            "total_units_after": round(total_units_after, 6),
            "portfolio_value_after": round(total_value_after, 2),
            "tactical_cash_reserve_after": self.state["tactical_cash_reserve"]
        }
        self.state["transactions"].append(tx_record)
        self._save_ledger()

        logger.info(
            f"[UNITIZED NAV DEPOSIT] Processed deposit of ${deposit_amount:,.2f}. "
            f"Issued {new_units_issued:,.4f} units at ${nav_before:.4f}/unit. "
            f"Total Units: {total_units_after:,.4f} | Total Value: ${total_value_after:,.2f}"
        )
        return tx_record

    def process_withdrawal(
        self,
        withdrawal_amount: float,
        portfolio_value_before_withdrawal: float,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Processes capital redemption:
        Redeems units at current NAV without altering NAV per unit.
        """
        now = timestamp or datetime.now(timezone.utc)
        withdrawal_amount = float(withdrawal_amount)
        if withdrawal_amount <= 0:
            raise ValueError(f"Withdrawal amount must be positive, got {withdrawal_amount}")

        existing_units = max(1e-6, float(self.state.get("total_units", 1.0)))
        nav_current = portfolio_value_before_withdrawal / existing_units

        units_redeemed = withdrawal_amount / nav_current
        total_units_after = max(0.0, existing_units - units_redeemed)
        total_value_after = max(0.0, portfolio_value_before_withdrawal - withdrawal_amount)

        self.state["total_units"] = round(total_units_after, 6)
        self.state["total_portfolio_value"] = round(total_value_after, 2)
        self.state["nav_per_unit"] = round(nav_current, 4)
        self.state["cumulative_withdrawals"] = round(float(self.state.get("cumulative_withdrawals", 0.0)) + withdrawal_amount, 2)

        tx_record = {
            "timestamp": now.isoformat(),
            "type": "WITHDRAWAL",
            "withdrawal_amount": withdrawal_amount,
            "nav_per_unit": round(nav_current, 4),
            "units_redeemed": round(units_redeemed, 6),
            "total_units_after": round(total_units_after, 6),
            "portfolio_value_after": round(total_value_after, 2)
        }
        self.state["transactions"].append(tx_record)
        self._save_ledger()

        logger.info(
            f"[UNITIZED NAV WITHDRAWAL] Processed withdrawal of ${withdrawal_amount:,.2f}. "
            f"Redeemed {units_redeemed:,.4f} units at ${nav_current:.4f}/unit."
        )
        return tx_record

    def deploy_opportunistic_dip_cash(
        self,
        deployment_pct: float = 0.50,
        as_of_date: Optional[date] = None
    ) -> float:
        """
        Opportunistic Dip Deployment:
        Deploys dry powder from the Tactical Cash Reserve when Phase 2 Mean-Reversion dips occur.
        Returns the dollar cash deployed.
        """
        curr_reserve = float(self.state.get("tactical_cash_reserve", 0.0))
        if curr_reserve <= 10.0:
            return 0.0

        cash_to_deploy = round(curr_reserve * min(1.0, max(0.0, deployment_pct)), 2)
        self.state["tactical_cash_reserve"] = round(curr_reserve - cash_to_deploy, 2)
        
        today = as_of_date or datetime.now(timezone.utc).date()
        self.state["last_dip_date"] = today.strftime("%Y-%m-%d")
        
        self.state["transactions"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "TACTICAL_DIP_DEPLOYMENT",
            "cash_deployed": cash_to_deploy,
            "tactical_cash_reserve_after": self.state["tactical_cash_reserve"]
        })
        self._save_ledger()

        logger.info(f"[TACTICAL DIP DEPLOY] Deployed ${cash_to_deploy:,.2f} from tactical cash buffer into dip buys.")
        return cash_to_deploy

    def evaluate_30_day_drip_feeder(
        self,
        current_date: Optional[date] = None,
        drip_fraction: float = 0.25
    ) -> float:
        """
        30-Day Tactical Drip Feeder:
        If the market enters an extended runaway bull market with no deep pullbacks for 30 consecutive days,
        gradually drips unspent SIP cash into top-ranked momentum compounders.
        """
        curr_date = current_date or datetime.now(timezone.utc).date()
        last_dip_str = self.state.get("last_dip_date")
        if not last_dip_str:
            self.state["last_dip_date"] = curr_date.strftime("%Y-%m-%d")
            self._save_ledger()
            return 0.0

        last_dip = datetime.strptime(last_dip_str, "%Y-%m-%d").date()
        days_without_dip = (curr_date - last_dip).days

        if days_without_dip < self.DRIP_FEEDER_TRIGGER_DAYS:
            return 0.0

        curr_reserve = float(self.state.get("tactical_cash_reserve", 0.0))
        if curr_reserve <= 50.0:
            return 0.0

        drip_cash = round(curr_reserve * drip_fraction, 2)
        self.state["tactical_cash_reserve"] = round(curr_reserve - drip_cash, 2)
        # Reset drip feeder timer
        self.state["last_dip_date"] = curr_date.strftime("%Y-%m-%d")

        self.state["transactions"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "TACTICAL_DRIP_FEEDER",
            "days_without_dip": days_without_dip,
            "drip_cash_deployed": drip_cash,
            "tactical_cash_reserve_after": self.state["tactical_cash_reserve"]
        })
        self._save_ledger()

        logger.info(
            f"[TACTICAL DRIP FEEDER] Market ran {days_without_dip} days without dip pullbacks. "
            f"Dripping ${drip_cash:,.2f} tactical cash into momentum compounders."
        )
        return drip_cash

    def get_fund_performance_metrics(self) -> Dict[str, Any]:
        """
        Computes accurate unitized fund metrics:
        - True Trading Return (% gain in NAV per unit)
        - Net Inflows (Deposits - Withdrawals)
        - True Trading PnL in Dollars (Portfolio Value - Net Inflows)
        """
        base_nav = float(self.state.get("base_nav_per_unit", self.INITIAL_NAV_PER_UNIT))
        current_nav = float(self.state.get("nav_per_unit", self.INITIAL_NAV_PER_UNIT))
        total_val = float(self.state.get("total_portfolio_value", 0.0))
        deposits = float(self.state.get("cumulative_deposits", 0.0))
        withdrawals = float(self.state.get("cumulative_withdrawals", 0.0))
        net_inflows = deposits - withdrawals

        true_trading_return_pct = ((current_nav - base_nav) / base_nav) * 100.0 if base_nav > 0 else 0.0
        true_trading_pnl_dollars = total_val - net_inflows

        return {
            "nav_per_unit": round(current_nav, 4),
            "base_nav_per_unit": round(base_nav, 4),
            "total_units": round(float(self.state.get("total_units", 0.0)), 6),
            "total_portfolio_value": round(total_val, 2),
            "tactical_cash_reserve": round(float(self.state.get("tactical_cash_reserve", 0.0)), 2),
            "cumulative_deposits": round(deposits, 2),
            "cumulative_withdrawals": round(withdrawals, 2),
            "net_inflows": round(net_inflows, 2),
            "true_trading_pnl_dollars": round(true_trading_pnl_dollars, 2),
            "true_trading_return_pct": round(true_trading_return_pct, 2)
        }
