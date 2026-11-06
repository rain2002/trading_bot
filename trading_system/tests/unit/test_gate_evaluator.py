"""
Unit Tests for Gate A & Gate B Clearance Evaluator (Chapter 2, Pod 3)
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)
Includes Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) Anti-Overfitting Defense.
"""

import os
import pytest
import pandas as pd
from trading_system.app.validation.gate_evaluator import GateEvaluator, GateAClearanceReport, GateBClearanceReport
from trading_system.app.validation.trial_logger import log_trial


class TestGateEvaluator:

    def test_gate_a_clearance_all_passed(self):
        """
        Verifies that a strategy clearing all statistical stress hurdles
        receives Gate A clearance.
        """
        report = GateEvaluator.evaluate_gate_a(
            oos_cagr=0.195,              # 19.5% >= 15.0%
            max_drawdown=-0.162,          # -16.2% >= -25.0%
            total_trades=142,             # 142 >= 100
            parameter_stability=0.88,     # 88% >= 80%
            monte_carlo_p5_dd=-0.22,      # -22% >= -30.0%
            sharpe_ratio=1.10             # High Sharpe
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

    def test_deflated_sharpe_50_trials_makes_marginal_result_fail(self, tmp_path):
        """
        Fiduciary Requirement: A marginal backtest result that passes with 1 trial
        MUST fail when 50 logged trials exist in trial_log.csv, preventing the
        parameter tuning loop from fooling itself through selection bias.
        """
        # Marginal strategy parameters (barely clears thresholds)
        marginal_cagr = 0.16             # 16.0% (just above 15% threshold)
        marginal_dd = -0.22              # -22.0% (within -25% threshold)
        marginal_trades = 110            # 110 (just above 100 threshold)
        marginal_stability = 0.82        # 82% (just above 80% threshold)
        marginal_mc_dd = -0.26           # -26.0% (within -30% threshold)
        marginal_sharpe = 0.48           # Marginal Sharpe ratio

        # Case 1: Fresh trial log with exactly 1 trial
        log_file_1 = tmp_path / "trial_log_1.csv"
        df_1 = pd.DataFrame([{
            "date": "2026-11-05 00:00:00",
            "commit_hash": "abc1234",
            "kelly_fraction": 0.40,
            "lookback_days": 90,
            "cagr_pct": 16.0,
            "max_drawdown_pct": -22.0,
            "sharpe_ratio": marginal_sharpe,
            "is_holdout_opened": False,
            "notes": "Single trial"
        }])
        df_1.to_csv(log_file_1, index=False)

        report_1 = GateEvaluator.evaluate_gate_a(
            oos_cagr=marginal_cagr,
            max_drawdown=marginal_dd,
            total_trades=marginal_trades,
            parameter_stability=marginal_stability,
            monte_carlo_p5_dd=marginal_mc_dd,
            sharpe_ratio=marginal_sharpe,
            trial_log_path=str(log_file_1)
        )

        # 1 trial: Selection bias adjustment is zero -> passes
        assert report_1.criteria["deflated_sharpe"]["passed"] is True
        assert report_1.passed is True

        # Case 2: 50 trials logged (the tuning loop searched 50 parameter variations)
        log_file_50 = tmp_path / "trial_log_50.csv"
        rows_50 = []
        for i in range(50):
            rows_50.append({
                "date": f"2026-11-05 00:{i:02d}:00",
                "commit_hash": f"hash_{i:04d}",
                "kelly_fraction": 0.20 + (i * 0.01),
                "lookback_days": 30 + i,
                "cagr_pct": 10.0 + (i * 0.1),
                "max_drawdown_pct": -25.0,
                "sharpe_ratio": 0.40 + (i * 0.005),
                "is_holdout_opened": False,
                "notes": f"Iteration {i}"
            })
        pd.DataFrame(rows_50).to_csv(log_file_50, index=False)

        report_50 = GateEvaluator.evaluate_gate_a(
            oos_cagr=marginal_cagr,
            max_drawdown=marginal_dd,
            total_trades=marginal_trades,
            parameter_stability=marginal_stability,
            monte_carlo_p5_dd=marginal_mc_dd,
            sharpe_ratio=marginal_sharpe,
            trial_log_path=str(log_file_50)
        )

        # 50 trials: Selection bias threshold E[max SR] exceeds 0.48 -> Deflated Sharpe drops to near 0% -> FAILS!
        assert report_50.passed is False
        assert report_50.criteria["deflated_sharpe"]["passed"] is False
        assert report_50.criteria["deflated_sharpe"]["trials_logged"] == 50
        assert report_50.criteria["deflated_sharpe"]["actual"] < 95.0
        assert "GATE A REJECTED" in report_50.summary
        assert "deflated_sharpe" in report_50.summary
