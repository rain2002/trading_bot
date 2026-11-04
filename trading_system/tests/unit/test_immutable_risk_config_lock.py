import os
import json
import time
import pytest
from pathlib import Path

from trading_system.app.config.stop_loss_manager import (
    StopLossManager,
    HARD_STOP_LOSS_PCT,
    TRAILING_STOP_TRIGGER_PCT,
    TRAILING_STOP_DISTANCE_PCT,
    BREAKEVEN_TRIGGER_PCT
)
from trading_system.app.risk.basic import (
    BasicRiskEngine,
    validate_risk_config,
    ImmutableRiskViolationError,
    CRO_MAX_DRAWDOWN_PCT,
    MAX_POSITIONS_CEILING,
    LONG_ONLY_MANDATE
)


def test_immutable_risk_constants_match_institutional_spec():
    """Asserts code-level constants match institutional risk floor specifications."""
    assert HARD_STOP_LOSS_PCT == -0.08
    assert TRAILING_STOP_TRIGGER_PCT == 0.15
    assert TRAILING_STOP_DISTANCE_PCT == 0.05
    assert BREAKEVEN_TRIGGER_PCT == 0.05

    assert StopLossManager.HARD_STOP_LOSS_PCT == -0.08
    assert StopLossManager.TRAILING_STOP_TRIGGER_PCT == 0.15
    assert StopLossManager.TRAILING_STOP_DISTANCE_PCT == 0.05
    assert StopLossManager.BREAKEVEN_TRIGGER_PCT == 0.05


def test_stop_loss_manager_rejects_looser_initial_config(tmp_path: Path):
    """
    Asserts StopLossManager rejects stop_loss_config.json initialized with looser values
    (e.g., -0.15 hard stop) and enforces immutable -0.08 floor.
    """
    tampered_file = str(tmp_path / "tampered_stop_loss.json")
    tampered_data = {
        "global_default_pct": -0.15,  # Looser than -0.08!
        "breakeven_gain_trigger_pct": 0.25,
        "overrides": {}
    }
    with open(tampered_file, "w", encoding="utf-8") as f:
        json.dump(tampered_data, f, indent=4)

    sl = StopLossManager(config_path=tampered_file)
    # Must reject -0.15 and enforce -0.08
    assert sl.get_global_default_pct() == -0.08
    assert sl.get_stop_loss_pct("AAPL") == -0.08


def test_stop_loss_manager_runtime_disk_mutation_lock(tmp_path: Path):
    """
    Asserts that if stop_loss_config.json is mutated on disk at runtime with looser values
    (e.g., modified to -0.20), StopLossManager detects tampering and enforces -0.08.
    """
    config_file = str(tmp_path / "runtime_lock_stop_loss.json")
    valid_data = {
        "global_default_pct": -0.08,
        "overrides": {}
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(valid_data, f, indent=4)

    sl = StopLossManager(config_path=config_file)
    assert sl.get_global_default_pct() == -0.08

    # Simulate runtime tampering on disk
    time.sleep(0.05)
    tampered_data = {
        "global_default_pct": -0.20,  # Extreme tampering
        "overrides": {}
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(tampered_data, f, indent=4)

    # Calling get_global_default_pct or get_stop_loss_pct must detect change and enforce -0.08
    assert sl.get_global_default_pct() == -0.08
    assert sl.get_stop_loss_pct("RELIANCE.NS") == -0.08


def test_set_global_default_rejects_looser_mutations(tmp_path: Path):
    """Asserts set_global_default_pct blocks values looser than HARD_STOP_LOSS_PCT."""
    config_file = str(tmp_path / "stop_loss_api_test.json")
    sl = StopLossManager(config_path=config_file)

    # Setting a safer/tighter stop is allowed (e.g. -5%)
    sl.set_global_default_pct(-0.05)
    assert sl.get_global_default_pct() == -0.05

    # Setting a looser stop (e.g. -15%) is rejected and clamped to -8% (-0.08)
    sl.set_global_default_pct(-0.15)
    assert sl.get_global_default_pct() == -0.08


def test_validate_risk_config_raises_on_immutable_breaches():
    """
    Asserts that validate_risk_config immediately raises ImmutableRiskViolationError
    when configurations attempt to widen stops, allow shorting, increase position ceiling,
    or loosen maximum drawdown.
    """
    # 1. Stop loss breach: -15% stop is looser than -8% floor
    with pytest.raises(ImmutableRiskViolationError, match="Configured stop loss"):
        validate_risk_config({"hard_stop": -0.15})

    with pytest.raises(ImmutableRiskViolationError, match="Configured stop loss"):
        validate_risk_config({"hard_stop_loss_pct": -0.12})

    # 2. Position ceiling breach: 15 positions exceeds 10 ceiling
    with pytest.raises(ImmutableRiskViolationError, match="exceeds fund ceiling"):
        validate_risk_config({"max_positions": 15})

    with pytest.raises(ImmutableRiskViolationError, match="exceeds fund ceiling"):
        validate_risk_config({"max_holdings": 12})

    # 3. Shorting violation: shorting is forbidden under Long-Only mandate
    with pytest.raises(ImmutableRiskViolationError, match="Short selling is strictly prohibited"):
        validate_risk_config({"allow_shorting": True})

    # 4. Max drawdown breach: -25% drawdown is looser than -18% ceiling
    with pytest.raises(ImmutableRiskViolationError, match="Max drawdown limit"):
        validate_risk_config({"cro_max_drawdown_pct": -0.25})

    # 5. Compliant configuration passes cleanly
    compliant_config = {
        "hard_stop": -0.08,
        "max_positions": 10,
        "allow_shorting": False,
        "cro_max_drawdown_pct": -0.18
    }
    assert validate_risk_config(compliant_config) is True

    # 6. BasicRiskEngine halts on violation during initialization
    with pytest.raises(ImmutableRiskViolationError):
        BasicRiskEngine(config={"hard_stop": -0.15})

