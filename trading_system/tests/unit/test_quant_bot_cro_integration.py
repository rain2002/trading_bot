"""
Unit Tests for Central CRO & Unitized NAV Integration in run_quant_bot.py
Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Phase 2, Modules 1-4)
"""

import os
import json
import pytest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch

from trading_system.app.risk.cro import ChiefRiskOfficer, CRORiskStatus
from trading_system.app.accounting.unitized_nav import UnitizedNAVEngine
from trading_system.app.notifications.notifier import QuantNotifier


class TestQuantBotCROIntegration:

    def test_cro_circuit_breaker_halts_new_entries(self, tmp_path):
        """
        When the CRO detects a single-day loss >= 2.0%, new entry targets
        must be gated and cleared, while leaving held positions for risk protection.
        """
        state_file = str(tmp_path / "cro_state.json")
        with open(state_file, "w") as f:
            json.dump({
                "high_water_mark": 100000.0,
                "start_of_day_nav": 100000.0,
                "last_calendar_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "confirmed_regime": "TRENDING_BULL"
            }, f)

        cro = ChiefRiskOfficer(state_file=state_file)
        # Drop 3% intraday (100k -> 97k)
        status = cro.evaluate_daily_cycle(current_nav=97000.0)

        assert status.daily_circuit_breaker_active is True
        assert status.can_enter_new_trades is False
        assert status.exposure_scale_factor == 0.0

        # Simulate run_quant_bot logic
        current_positions = {"AAPL": 10.0}
        target_weights = {"AAPL": 0.15, "NVDA": 0.15, "MSFT": 0.10}

        if not status.can_enter_new_trades or status.daily_circuit_breaker_active:
            target_weights = {s: w for s, w in target_weights.items() if s in current_positions}

        assert "NVDA" not in target_weights
        assert "MSFT" not in target_weights
        assert "AAPL" in target_weights

    def test_cro_drawdown_ladder_scale_factor(self, tmp_path):
        """
        When the CRO enters Step 1 (-10% Lynch: 0.70) or Step 2 (-18% Buffett: 0.10),
        target weights must be scaled proportionally.
        """
        state_file = str(tmp_path / "cro_state.json")
        with open(state_file, "w") as f:
            json.dump({
                "high_water_mark": 100000.0,
                "start_of_day_nav": 88000.0,
                "last_calendar_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "confirmed_regime": "TRENDING_BULL"
            }, f)

        cro = ChiefRiskOfficer(state_file=state_file)
        # 12% drawdown from HWM (100k -> 88k)
        status = cro.evaluate_daily_cycle(current_nav=88000.0)

        assert status.ladder_level == "LADDER_STEP_1_LYNCH"
        assert status.exposure_scale_factor == 0.70

        target_weights = {"AAPL": 0.20, "NVDA": 0.20}
        if status.exposure_scale_factor < 1.0:
            target_weights = {s: round(w * status.exposure_scale_factor, 4) for s, w in target_weights.items()}

        assert target_weights["AAPL"] == 0.14
        assert target_weights["NVDA"] == 0.14

    def test_cro_earnings_blackout_filters_prospective_buys(self, tmp_path):
        """
        Prospective buys scheduled to report earnings within 2 days must be rejected.
        """
        cro = ChiefRiskOfficer(state_file=str(tmp_path / "cro.json"))
        today = date(2026, 11, 4)
        earnings_dates = {
            "EARN_SOON": date(2026, 11, 5),   # 1 day away -> BLACKOUT
            "EARN_FAR": date(2026, 12, 1)     # 27 days away -> CLEAN
        }

        # Check filter
        assert cro.check_earnings_blackout("EARN_SOON", as_of_date=today, earnings_dates=earnings_dates) is False
        assert cro.check_earnings_blackout("EARN_FAR", as_of_date=today, earnings_dates=earnings_dates) is True
        assert cro.check_earnings_blackout("UNKNOWN_STOCK", as_of_date=today, earnings_dates=earnings_dates) is True

    def test_cro_circuit_band_rejection(self, tmp_path):
        """
        Stocks hitting daily circuit limits (+20% upper circuit) or on ASM/GSM must be blocked.
        """
        cro = ChiefRiskOfficer(state_file=str(tmp_path / "cro.json"))

        # Upper circuit hit (moved +19.8% on a 20% limit band)
        assert cro.check_exchange_surveillance_and_circuits("UPPER_LIMIT", price_change_pct=0.198) is False

        # ASM surveillance list
        assert cro.check_exchange_surveillance_and_circuits("SURVEILLANCE_STOCK", price_change_pct=0.02, is_asm_gsm_list=True) is False

        # Normal stock
        assert cro.check_exchange_surveillance_and_circuits("NORMAL_STOCK", price_change_pct=0.03) is True

    def test_unitized_nav_and_cro_in_daily_summary(self):
        """
        Verifies that QuantNotifier correctly formats and incorporates Unitized NAV,
        True Trading Return %, and CRO Drawdown Ladder tier.
        """
        notifier = QuantNotifier()
        with patch.object(notifier, "send_discord_message", return_value=True) as mock_discord:
            notifier.send_daily_summary(
                equity=105000.0,
                cash=25000.0,
                open_positions_count=3,
                executed_orders=[],
                today_pnl=1200.0,
                today_pnl_pct=1.15,
                overall_pnl=5000.0,
                overall_pnl_pct=5.0,
                regime_info="TRENDING_BULL (Max Exposure: 98%)",
                currency_symbol="$",
                cro_tier="NORMAL",
                nav_per_unit=105.0,
                true_trading_return_pct=5.0,
                tactical_cash_reserve=10000.0
            )

            assert mock_discord.called
            msg = mock_discord.call_args[0][0]
            assert "🏷️ **Unitized NAV:** $105.00/unit (True Trading Return: +5.00%)" in msg
            assert "🎯 **Tactical SIP Buffer:** $10,000.00 dry powder" in msg
            assert "🛡️ **CRO Drawdown Tier:** NORMAL" in msg
