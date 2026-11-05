"""
Unit Tests for Gate A & Gate B Clearance Evaluator (Chapter 2, Pod 3)
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)
"""

import pytest
from trading_system.app.validation.gate_evaluator import GateEvaluator, GateAClearanceReport, GateBClearanceReport


class TestGateEvaluator:

    def test_gate_a_clearance_all_passed(self):
        """
        Verifies that a strategy clearing all 5 statistical stress hurdles
        receives Gate A clearance.
        """
        report = GateEvaluator.evaluate_gate_a(
            oos_cagr=0.195,              # 19.5% >= 15.0%
            max_drawdown=-0.162,          # -16.2% >= -25.0%
            total_trades=142,             # 142 >= 100
            parameter_stability=0.88,     # 88% >= 80%
            monte_carlo_p5_dd=-0.22       # -22% >= -30.0%
        )

        assert report.passed is True
        assert "GATE A PASSED" in report.summary
        assert all(c["passed"] for c in report.criteria.values())

    def test_gate_a_fails_when_drawdown_exceeds_threshold(self):
        """
        Verifies that Gate A rejects any strategy where max drawdown breaches -25.0%.
        """
        report = GateEvaluator.evaluate_gate_a(
            oos_cagr=0.22,               # High return
            max_drawdown=-0.28,          # -28% breaches -25% limit
            total_trades=150,
            parameter_stability=0.85,
            monte_carlo_p5_dd=-0.35      # Breaches -30% limit
        )

        assert report.passed is False
        assert "GATE A REJECTED" in report.summary
        assert report.criteria["drawdown"]["passed"] is False
        assert report.criteria["monte_carlo_dd"]["passed"] is False

    def test_gate_b_graduation_clearance(self):
        """
        Verifies that when an incubation account completes 13 weeks with
        clean execution, drawdown < 10%, 0 SL breaches, and kill switch drill,
        Gate B clearance is granted.
        """
        report = GateEvaluator.evaluate_gate_b(
            weeks_logged=13,
            zero_crash_weeks=6,
            max_drawdown=-0.048,         # -4.8% < 10.0%
            sl_breaches=0,
            kill_switch_verified=True
        )

        assert report.passed is True
        assert "GATE B PASSED" in report.summary
        assert all(c["passed"] for c in report.criteria.values())

    def test_gate_b_pending_when_incubation_incomplete(self):
        """
        Verifies that Gate B remains pending if weeks_logged < 13 or kill switch is pending.
        """
        report = GateEvaluator.evaluate_gate_b(
            weeks_logged=4,              # In week 4 of 13
            zero_crash_weeks=4,
            max_drawdown=-0.03,
            sl_breaches=0,
            kill_switch_verified=False   # Kill switch drill not yet verified
        )

        assert report.passed is False
        assert "GATE B IN PROGRESS" in report.summary
        assert report.criteria["incubation_period"]["passed"] is False
        assert report.criteria["kill_switch_drill"]["passed"] is False
