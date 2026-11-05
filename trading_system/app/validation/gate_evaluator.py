"""
Institutional Gate A & Gate B Clearance Evaluator
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)

Fiduciary Principles:
Gate A (Statistical Stress Clearance):
1. Out-of-sample CAGR >= 15.0% after all fees, taxes, and 50% slippage stress.
2. Maximum peak-to-trough Drawdown <= -25.0%.
3. Total out-of-sample trades >= 100.
4. Parameter stability plateaus (performance within +/-20% param variation).
5. Monte Carlo worst 5th-percentile Drawdown within -30.0%.

Gate B (Live Forward Paper Clearance - 13 Weeks):
1. 13 consecutive weeks of forward paper execution on live quotes.
2. Minimum 4 consecutive weeks of zero crashed runs.
3. Live paper maximum drawdown <= -10.0%.
4. Zero unhandled hard stop-loss breaches (-8.0% mandate).
5. Emergency Discord kill-switch drill successfully verified.
"""

import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from trading_system.app.common.logger import get_logger

logger = get_logger("GateEvaluator")


@dataclass
class GateAClearanceReport:
    passed: bool
    oos_cagr: float
    max_drawdown: float
    total_trades: int
    parameter_stability: float
    monte_carlo_p5_dd: float
    criteria: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


@dataclass
class GateBClearanceReport:
    passed: bool
    weeks_logged: int
    zero_crash_weeks: int
    max_drawdown: float
    sl_breaches: int
    kill_switch_verified: bool
    criteria: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


class GateEvaluator:
    """
    Independent statistical and forward paper incubation gatekeeper.
    Controls clearance into Stage 2 (Real INR Capital).
    """

    # Gate A Hard Cutoffs
    GATE_A_MIN_CAGR: float = 0.15           # 15.0% Net CAGR
    GATE_A_MAX_DRAWDOWN: float = -0.25      # -25.0% Max Drawdown
    GATE_A_MIN_TRADES: int = 100            # 100 trades sample size
    GATE_A_MIN_STABILITY: float = 0.80      # 80% plateau stability
    GATE_A_WORST_P5_MC_DD: float = -0.30    # -30.0% Monte Carlo 5th percentile

    # Gate B Hard Cutoffs
    GATE_B_MIN_WEEKS: int = 13              # 13 weeks forward incubation
    GATE_B_CONSECUTIVE_STABLE_WEEKS: int = 4 # 4 weeks zero crashes
    GATE_B_MAX_INCUBATION_DD: float = -0.10 # -10.0% max DD in incubation

    @classmethod
    def evaluate_gate_a(
        cls,
        oos_cagr: float,
        max_drawdown: float,
        total_trades: int,
        parameter_stability: float,
        monte_carlo_p5_dd: float
    ) -> GateAClearanceReport:
        """
        Evaluates backtest / walk-forward candidate against Gate A criteria.
        """
        cagr_pass = oos_cagr >= cls.GATE_A_MIN_CAGR
        dd_pass = max_drawdown >= cls.GATE_A_MAX_DRAWDOWN
        trades_pass = total_trades >= cls.GATE_A_MIN_TRADES
        stability_pass = parameter_stability >= cls.GATE_A_MIN_STABILITY
        mc_pass = monte_carlo_p5_dd >= cls.GATE_A_WORST_P5_MC_DD

        all_passed = cagr_pass and dd_pass and trades_pass and stability_pass and mc_pass

        criteria = {
            "cagr": {
                "name": "Out-of-Sample Net CAGR (>= 15.0%)",
                "actual": round(oos_cagr * 100, 2),
                "threshold": round(cls.GATE_A_MIN_CAGR * 100, 2),
                "passed": cagr_pass
            },
            "drawdown": {
                "name": "Max Peak-to-Trough Drawdown (<= -25.0%)",
                "actual": round(max_drawdown * 100, 2),
                "threshold": round(cls.GATE_A_MAX_DRAWDOWN * 100, 2),
                "passed": dd_pass
            },
            "sample_size": {
                "name": "OOS Trade Sample Size (>= 100 trades)",
                "actual": total_trades,
                "threshold": cls.GATE_A_MIN_TRADES,
                "passed": trades_pass
            },
            "stability": {
                "name": "Parameter Plateau Stability (>= 80%)",
                "actual": round(parameter_stability * 100, 2),
                "threshold": round(cls.GATE_A_MIN_STABILITY * 100, 2),
                "passed": stability_pass
            },
            "monte_carlo_dd": {
                "name": "Monte Carlo 5th-Percentile Worst DD (<= -30.0%)",
                "actual": round(monte_carlo_p5_dd * 100, 2),
                "threshold": round(cls.GATE_A_WORST_P5_MC_DD * 100, 2),
                "passed": mc_pass
            }
        }

        if all_passed:
            summary = "GATE A PASSED: All 5 statistical stress hurdles cleared. Qualified for paper incubation."
        else:
            failed_keys = [k for k, v in criteria.items() if not v["passed"]]
            summary = f"GATE A REJECTED: Failed criteria: {', '.join(failed_keys)}."

        return GateAClearanceReport(
            passed=all_passed,
            oos_cagr=oos_cagr,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            parameter_stability=parameter_stability,
            monte_carlo_p5_dd=monte_carlo_p5_dd,
            criteria=criteria,
            summary=summary
        )

    @classmethod
    def evaluate_gate_b(
        cls,
        weeks_logged: int,
        zero_crash_weeks: int,
        max_drawdown: float,
        sl_breaches: int,
        kill_switch_verified: bool
    ) -> GateBClearanceReport:
        """
        Evaluates live forward paper trading results against Gate B incubation requirements.
        """
        weeks_pass = weeks_logged >= cls.GATE_B_MIN_WEEKS
        crashes_pass = zero_crash_weeks >= cls.GATE_B_CONSECUTIVE_STABLE_WEEKS
        dd_pass = max_drawdown >= cls.GATE_B_MAX_INCUBATION_DD
        sl_pass = sl_breaches == 0
        kill_pass = kill_switch_verified is True

        all_passed = weeks_pass and crashes_pass and dd_pass and sl_pass and kill_pass

        criteria = {
            "incubation_period": {
                "name": "Forward Incubation Duration (>= 13 Weeks)",
                "actual": weeks_logged,
                "threshold": cls.GATE_B_MIN_WEEKS,
                "passed": weeks_pass
            },
            "operational_stability": {
                "name": "Zero-Crash Consecutive Execution (>= 4 Weeks)",
                "actual": zero_crash_weeks,
                "threshold": cls.GATE_B_CONSECUTIVE_STABLE_WEEKS,
                "passed": crashes_pass
            },
            "drawdown_containment": {
                "name": "Paper Max Drawdown Containment (< 10.0%)",
                "actual": round(max_drawdown * 100, 2),
                "threshold": round(cls.GATE_B_MAX_INCUBATION_DD * 100, 2),
                "passed": dd_pass
            },
            "hard_stops": {
                "name": "Strict Hard Stop-Loss Enforcement (-8.0% Mandate)",
                "actual": f"{sl_breaches} unhandled",
                "threshold": "0 unhandled",
                "passed": sl_pass
            },
            "kill_switch_drill": {
                "name": "Emergency Discord Kill-Switch Verification",
                "actual": "VERIFIED" if kill_pass else "PENDING_DRILL",
                "threshold": "VERIFIED",
                "passed": kill_pass
            }
        }

        if all_passed:
            summary = "GATE B PASSED: 13-week institutional incubation verified. Ready for Stage 2 real INR capital allocation."
        else:
            failed_keys = [k for k, v in criteria.items() if not v["passed"]]
            summary = f"GATE B IN PROGRESS: Remaining hurdles: {', '.join(failed_keys)}."

        return GateBClearanceReport(
            passed=all_passed,
            weeks_logged=weeks_logged,
            zero_crash_weeks=zero_crash_weeks,
            max_drawdown=max_drawdown,
            sl_breaches=sl_breaches,
            kill_switch_verified=kill_switch_verified,
            criteria=criteria,
            summary=summary
        )
