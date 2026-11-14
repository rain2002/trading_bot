"""
Central Portfolio Manager & Cash Sleeve Engine (Phase 2)
=========================================================
Governed strictly by: PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113

Core Responsibilities:
1. Dynamic Capital Allocation: Distributes capital between active specialist bots and the cash sleeve.
2. Drawdown Throttle (2-Level Defense):
     - Level 1 (-15% DD): Risk assets reduced to 50% of target; 50% shifted to LIQUIDBEES.NS.
     - Level 2 (-30% DD): Risk assets reduced to 25% of target; 75% shifted to LIQUIDBEES.NS.
3. Hard Kill Switch (-40% DD): 100% of capital recalled to LIQUIDBEES.NS, flips to HALTED.
     No restart without explicit human approval.
4. Gradual Re-risking: Moves up ONE level only after drawdown recovers by +5 percentage points
     for 21 consecutive trading days. Never skips a level.
5. Daily Fiduciary Reconciliation: Compares Manager total NAV against the sum of Bot NAVs.
     A gap > 0.1% pauses all trading and flags an alert.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.common.interfaces import BotReport, ManagerInterface

logger = logging.getLogger("PortfolioManager")

# Protocol Thresholds
THROTTLE_L1_TRIGGER = -0.15      # -15% drawdown
THROTTLE_L1_RISK_SCALE = 0.50    # 50% risk exposure
THROTTLE_L1_RECOVERY = -0.10     # -10% drawdown (5 pts better)

THROTTLE_L2_TRIGGER = -0.30      # -30% drawdown
THROTTLE_L2_RISK_SCALE = 0.25    # 25% risk exposure
THROTTLE_L2_RECOVERY = -0.25     # -25% drawdown (5 pts better)

KILL_SWITCH_TRIGGER = -0.40      # -40% hard stop
KILL_SWITCH_RISK_SCALE = 0.0     # 0% risk exposure (100% to LIQUIDBEES)

RE_RISK_CONSECUTIVE_DAYS = 21    # 21 trading days required to de-throttle one level
RECONCILIATION_MAX_GAP = 0.001   # 0.1% max permissible gap


class PortfolioManagerEngine(ManagerInterface):
    """
    Production Manager Engine implementing ManagerInterface.
    Governs multi-bot capital routing, risk throttling, kill-switch,
    re-risking and daily reconciliation.
    """
    def __init__(
        self,
        target_shares: Optional[Dict[str, float]] = None,
        initial_capital: float = 80000.0,
        state_file: Optional[str] = None,
        policy: str = "FIXED_SHARES_PLUS_KILL_SWITCH"
    ):
        data_dir = os.path.join(PROJECT_ROOT, "trading_system", "data")
        self.state_file = state_file or os.path.join(data_dir, "manager_state.json")
        self.initial_capital = float(initial_capital)
        self.policy = policy
        # Default: ETF Bot gets 100% of deployable capital
        self.target_shares = target_shares or {"ETF_AND_GOLD": 1.0}
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    if "policy" not in data:
                        data["policy"] = self.policy
                    return data
            except Exception as e:
                logger.error(f"Error reading manager state: {e}. Reinitializing.")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
            "phase": "PHASE_2",
            "policy": self.policy,
            "unitized_nav": 100.0,
            "hwm_unit_nav": 100.0,
            "current_drawdown": 0.0,
            "max_drawdown": 0.0,
            "throttle_level": 0,  # 0: Normal, 1: Moderate (-15%), 2: Severe (-30%), 3: Killed (-40%)
            "consecutive_recovery_days": 0,
            "is_halted": False,
            "halt_reason": None,
            "human_override_required": False,
            "last_reconciliation_gap_pct": 0.0,
            "last_rebalance_date": None,
            "current_shares": {"ETF_AND_GOLD": 1.0, "CASH_SLEEVE": 0.0},
            "last_update": now_iso
        }

    def _save_state(self):
        self.state["last_update"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def reconcile_portfolio(
        self,
        bot_navs: Dict[str, float],
        manager_nav: float
    ) -> Tuple[bool, float]:
        """
        Daily check that Manager NAV equals the sum of Bot NAVs within 0.1%.
        Returns: (is_passed, gap_fraction)
        """
        total_bot_nav = sum(bot_navs.values())
        if manager_nav <= 0:
            return True, 0.0

        gap = abs(manager_nav - total_bot_nav) / manager_nav
        self.state["last_reconciliation_gap_pct"] = round(gap * 100.0, 4)

        if gap > RECONCILIATION_MAX_GAP:
            logger.error(
                f"RECONCILIATION GAP BREACH: Gap of {gap*100:.3f}% exceeds maximum permissible {RECONCILIATION_MAX_GAP*100:.1f}%! "
                f"Manager NAV: INR {manager_nav:,.2f} vs Sum of Bots: INR {total_bot_nav:,.2f}"
            )
            return False, gap
        return True, gap

    def evaluate_shares(
        self,
        as_of: pd.Timestamp,
        reports: Dict[str, BotReport],
        nav_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Evaluates capital shares across specialist bots and the cash sleeve.
        Enforces drawdown throttle, kill-switch, stale report checks, and re-risking.
        """
        # 1. Daily Reconciliation Guard
        manager_total_val = float(nav_state.get("total_portfolio_value", self.initial_capital))
        bot_navs = {k: r.nav for k, r in reports.items()}
        rec_pass, gap = self.reconcile_portfolio(bot_navs, manager_total_val)
        if not rec_pass:
            self.state["is_halted"] = True
            self.state["halt_reason"] = f"RECONCILIATION_GAP_BREACH: {gap*100:.3f}% > 0.1%"
            self._save_state()
            return {"CASH_SLEEVE": 1.0}

        # 2. Update Unitized NAV & Lifetime High-Water Mark
        unit_nav = float(nav_state.get("nav_per_unit", 100.0))
        hwm = max(float(self.state.get("hwm_unit_nav", 100.0)), unit_nav)
        dd = (unit_nav - hwm) / hwm

        self.state["unitized_nav"] = round(unit_nav, 4)
        self.state["hwm_unit_nav"] = round(hwm, 4)
        self.state["current_drawdown"] = round(dd, 4)
        self.state["max_drawdown"] = round(min(float(self.state.get("max_drawdown", 0.0)), dd), 4)

        # 3. Hard Kill Switch Check (-40%)
        if dd <= KILL_SWITCH_TRIGGER or self.state.get("is_halted", False):
            self.state["throttle_level"] = 3
            self.state["is_halted"] = True
            if not self.state.get("halt_reason"):
                self.state["halt_reason"] = f"KILL_SWITCH_TRIGGERED: Drawdown {dd*100:.2f}% breached -40.0% hard stop"
            self.state["human_override_required"] = True
            self.state["current_shares"] = {"CASH_SLEEVE": 1.0}
            self._save_state()
            logger.critical(f"MANAGER HALTED: {self.state['halt_reason']}. 100% capital routed to LIQUIDBEES.NS.")
            return {"CASH_SLEEVE": 1.0}

        # 4. Drawdown Throttle Transitions (Only active under THROTTLE_AND_KILL_SWITCH policy)
        current_level = int(self.state.get("throttle_level", 0))
        recovery_days = int(self.state.get("consecutive_recovery_days", 0))

        if self.policy == "THROTTLE_AND_KILL_SWITCH":
            # Downward Risk-Off Transitions (Immediate)
            if dd <= THROTTLE_L2_TRIGGER:
                if current_level < 2:
                    logger.warning(f"THROTTLE LEVEL 2 ACTIVATED: Drawdown {dd*100:.2f}% breached -30.0%. Cutting risk to 25%.")
                current_level = 2
                recovery_days = 0
            elif dd <= THROTTLE_L1_TRIGGER:
                if current_level < 1:
                    logger.warning(f"THROTTLE LEVEL 1 ACTIVATED: Drawdown {dd*100:.2f}% breached -15.0%. Cutting risk to 50%.")
                if current_level == 0:
                    current_level = 1
                    recovery_days = 0

            # Upward Re-risking Transitions (Requires 21 days +5 pts better, never skips a level)
            if current_level == 2:
                if dd >= THROTTLE_L2_RECOVERY:  # >= -25%
                    recovery_days += 1
                    if recovery_days >= RE_RISK_CONSECUTIVE_DAYS:
                        current_level = 1
                        recovery_days = 0
                        logger.info(f"RE-RISKING: Level 2 -> Level 1 after {RE_RISK_CONSECUTIVE_DAYS} days above -25%.")
                else:
                    recovery_days = 0
            elif current_level == 1:
                if dd >= THROTTLE_L1_RECOVERY:  # >= -10%
                    recovery_days += 1
                    if recovery_days >= RE_RISK_CONSECUTIVE_DAYS:
                        current_level = 0
                        recovery_days = 0
                        logger.info(f"RE-RISKING: Level 1 -> Level 0 after {RE_RISK_CONSECUTIVE_DAYS} days above -10%.")
                else:
                    recovery_days = 0

        self.state["throttle_level"] = current_level
        self.state["consecutive_recovery_days"] = recovery_days

        # 5. Compute Risk Exposure Multiplier
        if current_level == 0:
            risk_scale = 1.0
        elif current_level == 1:
            risk_scale = THROTTLE_L1_RISK_SCALE  # 0.50
        elif current_level == 2:
            risk_scale = THROTTLE_L2_RISK_SCALE  # 0.25
        else:
            risk_scale = KILL_SWITCH_RISK_SCALE  # 0.0

        # 6. Allocate Shares Across Bots & Cash Sleeve
        shares: Dict[str, float] = {}
        total_risk_allocated = 0.0

        for bot_id, target_share in self.target_shares.items():
            report = reports.get(bot_id)
            if report is None or report.stale:
                # Stale or missing report: freeze bot allocation to 0.0
                logger.warning(f"Bot {bot_id} report missing or stale. Freezing allocation.")
                shares[bot_id] = 0.0
                continue

            # In Phase 2: Bot must have at least GATE_B_PAPER cleared for paper allocation
            if report.gate_status in ["GATE_B_PAPER", "LIVE_APPROVED"]:
                eff_share = round(target_share * risk_scale, 4)
                shares[bot_id] = eff_share
                total_risk_allocated += eff_share
            else:
                shares[bot_id] = 0.0

        # Unallocated capital defaults to Cash Sleeve (LIQUIDBEES.NS)
        cash_share = round(max(0.0, 1.0 - total_risk_allocated), 4)
        shares["CASH_SLEEVE"] = cash_share

        self.state["current_shares"] = shares
        self._save_state()
        return shares

    def resume_approved(self):
        """Allows human boss override to resume trading after a kill-switch halt."""
        self.state["is_halted"] = False
        self.state["halt_reason"] = None
        self.state["human_override_required"] = False
        self.state["throttle_level"] = 2  # Restart cautiously at Level 2
        self.state["consecutive_recovery_days"] = 0
        self._save_state()
        logger.info("Human boss override received: Resuming portfolio trading at Throttle Level 2.")

    def get_status(self) -> Dict[str, Any]:
        return {
            "throttle_level": self.state.get("throttle_level", 0),
            "current_drawdown": self.state.get("current_drawdown", 0.0),
            "hwm_unit_nav": self.state.get("hwm_unit_nav", 100.0),
            "is_halted": self.state.get("is_halted", False),
            "halt_reason": self.state.get("halt_reason"),
            "consecutive_recovery_days": self.state.get("consecutive_recovery_days", 0),
            "last_reconciliation_gap_pct": self.state.get("last_reconciliation_gap_pct", 0.0),
            "current_shares": self.state.get("current_shares", {})
        }
