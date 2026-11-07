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

    def test_gate_b_guard_refuses_without_signed_certification(self, tmp_path):
        """
        Verifies that Gate B evaluation is strictly refused when no signed Gate A
        certification file exists on disk.
        """
        report = GateEvaluator.evaluate_gate_b(
            weeks_logged=14,
            zero_crash_weeks=6,
            max_drawdown=-0.04,
            sl_breaches=0,
            kill_switch_verified=True,
            variant_id="Variant_Uncertified",
            protocol_hash="AABBCCDD"
        )
        assert report.passed is False
        assert "GATE B REFUSED" in report.summary
        assert report.criteria["gate_a_prerequisite"]["passed"] is False

    def test_gate_b_guard_cannot_be_fooled_by_trial_log_string_injection(self, tmp_path):
        """
        Verifies that typing 'Gate A PASS' into trial_log.csv DOES NOT bypass Gate B guard.
        The guard strictly checks for an authenticated, signed result file.
        """
        fake_log = tmp_path / "trial_log.csv"
        df = pd.DataFrame([{
            "date": "2026-11-07 00:00:00",
            "commit_hash": "spoofed1",
            "kelly_fraction": 0.40,
            "lookback_days": 90,
            "cagr_pct": 25.0,
            "max_drawdown_pct": -10.0,
            "sharpe_ratio": 2.0,
            "is_holdout_opened": False,
            "notes": "Variant 2 Gate A PASS Audited Clearance"
        }])
        df.to_csv(fake_log, index=False)

        # Passing trial_log_path with fake string must still return False
        cleared = GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="Variant 2",
            cert_dir=str(tmp_path)
        )
        assert cleared is False

    def test_india_variant_2_cannot_pass_gate_a_certification_guard(self, tmp_path):
        """
        Verifies that India Growth Pod Variant 2 (which had -27.6% drawdown and opened holdout)
        cannot be certified and is refused clearance for Gate B.
        """
        # 1. Attempting to certify Variant 2 with -27.64% drawdown must fail
        cert_path = GateEvaluator.certify_gate_a_result(
            variant_id="India_Variant_2",
            protocol_hash="HASH1234",
            cagr_pct=17.96,
            max_drawdown_pct=-27.64,  # Breaches -25.0% Gate A limit!
            total_trades=116,
            is_holdout_opened=True,   # Breaches holdout integrity!
            cert_dir=str(tmp_path)
        )
        assert cert_path is None

        # 2. Gate B verification must return False
        assert GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="India_Variant_2",
            cert_dir=str(tmp_path)
        ) is False

    def test_tampered_gate_a_certificate_is_rejected(self, tmp_path):
        """
        Verifies that tampering with a signed Gate A certificate payload invalidates HMAC
        and blocks Gate B clearance.
        """
        cert_path = GateEvaluator.certify_gate_a_result(
            variant_id="Variant_Valid",
            protocol_hash="VALIDHASH123",
            cagr_pct=18.5,
            max_drawdown_pct=-18.0,
            total_trades=120,
            is_holdout_opened=False,
            cert_dir=str(tmp_path)
        )
        assert cert_path is not None
        assert os.path.exists(cert_path)

        # Tamper with the drawdown in the JSON file without updating HMAC
        import json
        with open(cert_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["cagr_pct"] = 35.0  # Tampered
        with open(cert_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Verification must detect tampering and refuse
        cleared = GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="Variant_Valid",
            cert_file_path=cert_path
        )
        assert cleared is False

    def test_genuine_gate_a_pass_authorizes_gate_b(self, tmp_path):
        """
        Verifies that an authentic signed Gate A certificate clearing all hurdles
        successfully passes verification and permits Gate B clearance.
        """
        cert_path = GateEvaluator.certify_gate_a_result(
            variant_id="Champion_Variant",
            protocol_hash="CHAMPION_HASH_99",
            cagr_pct=19.2,
            max_drawdown_pct=-16.5,
            total_trades=150,
            is_holdout_opened=False,
            cert_dir=str(tmp_path)
        )
        assert cert_path is not None

        cleared = GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="Champion_Variant",
            protocol_hash="CHAMPION_HASH_99",
            cert_file_path=cert_path
        )
        assert cleared is True

    def test_gate_a_signing_key_from_environment(self, tmp_path, monkeypatch):
        """
        Verifies that GATE_A_SIGNING_KEY is loaded from environment secrets,
        and that a key mismatch between signing and verification refuses clearance.
        """
        # 1. Sign certificate using a custom secret key from environment
        monkeypatch.setenv("GATE_A_SIGNING_KEY", "SUPER_SECRET_PROD_KEY_987654321")
        cert_path = GateEvaluator.certify_gate_a_result(
            variant_id="Env_Key_Variant",
            protocol_hash="HASH_ENV_123",
            cagr_pct=18.0,
            max_drawdown_pct=-15.0,
            total_trades=110,
            is_holdout_opened=False,
            cert_dir=str(tmp_path)
        )
        assert cert_path is not None

        # 2. Verification succeeds with matching environment secret
        cleared = GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="Env_Key_Variant",
            protocol_hash="HASH_ENV_123",
            cert_file_path=cert_path
        )
        assert cleared is True

        # 3. Verification strictly fails if environment secret changes
        monkeypatch.setenv("GATE_A_SIGNING_KEY", "DIFFERENT_UNAUTHORIZED_KEY_000")
        tampered_clearance = GateEvaluator.verify_gate_a_clearance_for_gate_b(
            variant_id="Env_Key_Variant",
            protocol_hash="HASH_ENV_123",
            cert_file_path=cert_path
        )
        assert tampered_clearance is False

    def test_gate_a_signing_key_enforced_in_production(self, monkeypatch):
        """
        Verifies that in strict production mode (ENV=production), missing GATE_A_SIGNING_KEY
        raises ValueError, preventing unauthenticated certifications.
        """
        from trading_system.app.validation.gate_evaluator import _get_gate_a_signing_key

        monkeypatch.delenv("GATE_A_SIGNING_KEY", raising=False)
        monkeypatch.delenv("GATE_A_SECRET", raising=False)
        monkeypatch.setenv("ENV", "production")

        with pytest.raises(ValueError, match="GATE_A_SIGNING_KEY or GATE_A_SECRET environment variable is missing"):
            _get_gate_a_signing_key()

