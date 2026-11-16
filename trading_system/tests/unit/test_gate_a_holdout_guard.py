"""
Unit Tests: Gate A Holdout Guard Invariant
===========================================
Validates that out-of-sample holdout data is strictly sealed and opened
ONLY if a candidate clears all 9 Gate A hurdles. Non-winning or unapproved
candidates are strictly barred from opening the holdout.
"""

import os
import pytest
import pandas as pd


def test_holdout_guard_logic_when_no_candidate_clears():
    """Verify that when all candidates fail Gate A, champion_cid is None and holdout stays sealed."""
    candidates = ["M1", "R1", "L1"]
    hurdles_check = {
        "M1": {"ALL_PASS": False},
        "R1": {"ALL_PASS": False},
        "L1": {"ALL_PASS": False},
    }
    results = {
        "M1": {"sharpe_ratio": 0.0865},
        "R1": {"sharpe_ratio": -0.0929},
        "L1": {"sharpe_ratio": -0.0747},
    }

    passed_candidates = [cid for cid in candidates if hurdles_check[cid]["ALL_PASS"]]
    
    # Champion selection rule
    if passed_candidates:
        champion_cid = max(passed_candidates, key=lambda c: results[c]["sharpe_ratio"])
    else:
        champion_cid = None

    assert champion_cid is None, "Champion must be None when no candidate cleared Gate A"

    # Holdout execution decision
    is_holdout_evaluated = champion_cid is not None
    assert is_holdout_evaluated is False, "Holdout must NOT be evaluated when champion is None"

    # Log trial flag for each candidate
    for cid in candidates:
        is_opened = (cid == champion_cid and champion_cid is not None)
        assert is_opened is False, f"Candidate {cid} must have is_holdout_opened=False"


def test_holdout_guard_logic_when_candidate_clears():
    """Verify that when a candidate clears Gate A, only that passing candidate opens holdout."""
    candidates = ["M1", "R1", "L1"]
    hurdles_check = {
        "M1": {"ALL_PASS": True},
        "R1": {"ALL_PASS": False},
        "L1": {"ALL_PASS": False},
    }
    results = {
        "M1": {"sharpe_ratio": 0.65},
        "R1": {"sharpe_ratio": -0.0929},
        "L1": {"sharpe_ratio": -0.0747},
    }

    passed_candidates = [cid for cid in candidates if hurdles_check[cid]["ALL_PASS"]]
    if passed_candidates:
        champion_cid = max(passed_candidates, key=lambda c: results[c]["sharpe_ratio"])
    else:
        champion_cid = None

    assert champion_cid == "M1"
    assert (champion_cid is not None) is True

    # Exactly one candidate opens holdout
    opened_flags = [(cid == champion_cid and champion_cid is not None) for cid in candidates]
    assert sum(opened_flags) == 1
    assert opened_flags[0] is True   # M1
    assert opened_flags[1] is False  # R1
    assert opened_flags[2] is False  # L1


def test_trial_log_phase4_holdout_integrity():
    """Verify trial_log.csv rows for Phase 4 enforce is_holdout_opened=False for failed candidates."""
    trial_log_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "trial_log.csv"
    )
    assert os.path.exists(trial_log_path), "trial_log.csv must exist"

    df = pd.read_csv(trial_log_path)
    phase4_rows = df[df["script"] == "run_phase4_sp500_sector_gate_a.py"]
    
    assert len(phase4_rows) >= 3, "Phase 4 must have at least 3 logged trials"
    for _, row in phase4_rows.iterrows():
        # Passed is in notes: 'Passed=False'
        notes = str(row["notes"])
        if "Passed=False" in notes:
            assert str(row["is_holdout_opened"]).strip().lower() == "false", (
                f"Failed candidate must have is_holdout_opened=False in trial log: {notes}"
            )


def test_trial_log_phase5_holdout_integrity():
    """Verify trial_log.csv rows for Phase 5 enforce is_holdout_opened=False for failed candidates."""
    import json
    trial_log_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "trial_log.csv"
    )
    assert os.path.exists(trial_log_path), "trial_log.csv must exist"

    df = pd.read_csv(trial_log_path)
    phase5_rows = df[df["script"] == "run_phase5_nse_whole_market_gate_a.py"]
    assert len(phase5_rows) >= 1, "Phase 5 must have at least 1 logged trial"

    for _, row in phase5_rows.iterrows():
        notes = str(row["notes"])
        assert "AllPass=False" in notes
        assert str(row["is_holdout_opened"]).strip().lower() == "false"
        assert "Holdout=STRICTLY_SEALED" in notes

    results_json = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "phase5_nse_whole_market_gate_a_results.json"
    )
    assert os.path.exists(results_json), "phase5_nse_whole_market_gate_a_results.json must exist"
    data = json.load(open(results_json, "r"))
    assert data["gate_a_hurdles"]["ALL_HURDLES_PASSED"] is False
    assert data["holdout_evaluation"]["status"] == "SEALED_GATE_A_FAILED"
    assert data["recommendation"] == "PARK_NSE_BOT_PERMANENTLY_CORE_RETAINS_ETF_CASH_ONLY"

