"""
Unit Tests for Emergency Kill Switch and Verification Drill (Chapter 2, Pod 3)
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 2, Item 2 & Chapter 2)
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from trading_system.app.risk.cro import ChiefRiskOfficer
from trading_system.scripts.emergency_kill_switch import main


class TestEmergencyKillSwitch:

    def test_cro_trigger_emergency_kill_switch(self, tmp_path):
        """
        Verifies that trigger_emergency_kill_switch sets emergency_halt_active,
        quarantines capital, and dispatches a critical Discord alert.
        """
        state_file = str(tmp_path / "cro_state.json")
        mock_notifier = MagicMock()
        cro = ChiefRiskOfficer(state_file=state_file, notifier=mock_notifier)

        cro.trigger_emergency_kill_switch(reason="Test Emergency Trigger")

        assert cro.state["emergency_halt_active"] is True
        assert cro.state["last_kill_switch_event"]["reason"] == "Test Emergency Trigger"
        assert mock_notifier.send_discord_alert.called

        status = cro.evaluate_daily_cycle(current_nav=100000.0)
        assert status.can_enter_new_trades is False
        assert status.exposure_scale_factor == 0.0
        assert status.ladder_level == "EMERGENCY_HALT"

    def test_cro_reset_emergency_halt(self, tmp_path):
        """
        Verifies that reset_emergency_halt restores normal operations.
        """
        state_file = str(tmp_path / "cro_state.json")
        cro = ChiefRiskOfficer(state_file=state_file)

        cro.trigger_emergency_kill_switch(reason="Test Trigger")
        assert cro.state["emergency_halt_active"] is True

        cro.reset_emergency_halt()
        assert cro.state["emergency_halt_active"] is False

        status = cro.evaluate_daily_cycle(current_nav=100000.0)
        assert status.can_enter_new_trades is True

    def test_cro_verify_kill_switch_drill(self, tmp_path):
        """
        Verifies that verify_kill_switch_drill satisfies Gate B Criterion 5
        and dispatches confirmation alert.
        """
        state_file = str(tmp_path / "cro_state.json")
        mock_notifier = MagicMock()
        cro = ChiefRiskOfficer(state_file=state_file, notifier=mock_notifier)

        drill_record = cro.verify_kill_switch_drill()

        assert cro.state["kill_switch_drill_verified"] is True
        assert drill_record["drill_status"] == "VERIFIED"
        assert mock_notifier.send_discord_alert.called
        assert "KILL-SWITCH DRILL VERIFIED" in mock_notifier.send_discord_alert.call_args[1]["title"]
