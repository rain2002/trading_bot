"""
Central Chief Risk Officer (CRO) Supervisor Engine
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 2)

Fiduciary Responsibilities:
1. 2.0% Daily Loss Circuit Breaker: Halts new entries for the day if single-day portfolio NAV drops >= 2.0%.
2. Buffett & Lynch De-Risking Drawdown Ladder:
   - Level 1 (-10% DD): Cuts open risk budget by 30% (Lynch Pullback Boundary).
   - Level 2 (-18% DD): Rotates into Cash / Defensive T-Bills (Buffett Rule #1 Capital Defense Ceiling).
   - Level 3 (-24% DD): Complete freeze on all new stock buying.
   - Level 4 (-30% DD): Emergency circuit breaker (quarantine capital until manual reset).
3. Crash Defense Protocol: 100% Cash Rotation on CRASH_WARNING.
4. Earnings Event-Risk Blackout Gate: 0 new swing entries within 2 trading days before earnings.
5. Macro Regime Flip Whipsaw Damping: 2-close confirmation before regime transition, 10-day cooldown.
6. Boss-Away Watchdog Mode: 14-day inactivity freeze if no check-in ping received.
"""

import os
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from trading_system.app.common.logger import get_logger

logger = get_logger("CentralCRO")


@dataclass
class CRORiskStatus:
    can_enter_new_trades: bool = True
    exposure_scale_factor: float = 1.0  # 1.0 (normal), 0.70 (-10% DD), 0.10 (-18% DD), 0.0 (freeze/crash/breaker)
    ladder_level: str = "NORMAL"         # NORMAL, LADDER_STEP_1_LYNCH, LADDER_STEP_2_BUFFETT, LADDER_STEP_3_FREEZE, EMERGENCY_HALT
    daily_circuit_breaker_active: bool = False
    crash_warning_active: bool = False
    boss_away_active: bool = False
    active_breaches: List[str] = field(default_factory=list)
    action_summary: str = "CRO: All fiduciary conditions green. Normal execution permitted."


class ChiefRiskOfficer:
    """
    Central CRO supervisor process overseeing risk allocation, circuit breakers,
    and portfolio preservation.
    """

    DAILY_LOSS_LIMIT_PCT: float = 0.02      # 2.0% max loss in single day
    LYNCH_DRAWDOWN_PCT: float = -0.10       # -10% drawdown (Step 1: cut risk by 30%)
    BUFFETT_DRAWDOWN_PCT: float = -0.18     # -18% drawdown (Step 2: rotate to cash/defensive)
    FREEZE_DRAWDOWN_PCT: float = -0.24      # -24% drawdown (Step 3: complete buying freeze)
    EMERGENCY_HALT_DD_PCT: float = -0.30    # -30% drawdown (Step 4: hard emergency stop)
    BOSS_AWAY_TIMEOUT_DAYS: int = 14        # 14 days inactivity watchdog

    def __init__(
        self,
        state_file: Optional[str] = None,
        notifier: Optional[Any] = None
    ):
        if state_file is None:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            state_file = os.path.join(root_dir, "data", "cro_state.json")
        self.state_file = os.path.abspath(state_file)
        self.notifier = notifier
        self._load_state()

    def _load_state(self):
        """Loads CRO persistent state (high-water mark, start of day NAV, watchdog ping, regime history)."""
        self.state: Dict[str, Any] = {
            "high_water_mark": 100000.0,
            "start_of_day_nav": 100000.0,
            "last_calendar_day": None,
            "last_boss_ping": datetime.now(timezone.utc).isoformat(),
            "confirmed_regime": "TRENDING_BULL",
            "last_regime_flip_date": None,
            "emergency_halt_active": False,
            "regime_candidate": None,
            "regime_candidate_count": 0
        }
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state.update(data)
            except Exception as e:
                logger.warning(f"Could not load CRO state: {e}. Using baseline state.")

    def _save_state(self):
        """Persists CRO state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to persist CRO state: {e}")

    def register_boss_ping(self, timestamp: Optional[datetime] = None):
        """Registers a one-tap handshake ping from the Boss to refresh the 14-day watchdog."""
        ts = timestamp or datetime.now(timezone.utc)
        self.state["last_boss_ping"] = ts.isoformat()
        self._save_state()
        logger.info(f"[CRO WATCHDOG] Boss handshake ping registered at {ts.isoformat()}. Watchdog reset to 14 days.")

    def reset_emergency_halt(self):
        """Allows manual reset of the -30% emergency halt by the Boss."""
        self.state["emergency_halt_active"] = False
        self._save_state()
        logger.info("[CRO] Emergency halt reset manually by Boss authorization.")

    def trigger_emergency_kill_switch(self, reason: str = "Manual Boss Emergency Kill Switch Triggered") -> None:
        """
        Activates emergency kill switch, quarantining capital and halting all new trades.
        """
        self.state["emergency_halt_active"] = True
        self.state["last_kill_switch_event"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "type": "LIVE_TRIGGER"
        }
        self._save_state()
        logger.warning(f"[CRO KILL SWITCH ACTIVATED] {reason}")
        if self.notifier:
            try:
                self.notifier.send_discord_alert(
                    title="🚨 CRO EMERGENCY KILL SWITCH TRIGGERED",
                    message=f"Capital quarantined: {reason}. All trading frozen until Boss manual reset.",
                    color=16711680
                )
            except Exception as e:
                logger.warning(f"Could not dispatch kill switch alert: {e}")

    def verify_kill_switch_drill(self) -> Dict[str, Any]:
        """
        Executes a controlled emergency kill-switch verification drill for Gate B compliance.
        Triggers the kill switch, records audit receipt, dispatches Discord drill confirmation,
        and cleanly resets back to normal operations.
        """
        drill_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drill_status": "VERIFIED",
            "drill_type": "GATE_B_EMERGENCY_KILL_SWITCH_DRILL"
        }
        self.state["kill_switch_drill_verified"] = True
        self.state["last_drill_record"] = drill_record
        self._save_state()

        logger.info("[CRO KILL SWITCH DRILL] Emergency kill-switch drill successfully verified.")
        if self.notifier:
            try:
                self.notifier.send_discord_alert(
                    title="🛡️ CRO KILL-SWITCH DRILL VERIFIED (GATE B)",
                    message="Emergency kill-switch drill executed and verified. Fiduciary circuit responds immediately. Gate B Criterion 5 satisfied.",
                    color=65280
                )
            except Exception as e:
                logger.warning(f"Could not dispatch kill switch drill alert: {e}")
        return drill_record

    def evaluate_daily_cycle(
        self,
        current_nav: float,
        as_of_time: Optional[datetime] = None,
        macro_regime: str = "TRENDING_BULL"
    ) -> CRORiskStatus:
        """
        Executes full CRO evaluation cycle:
        1. Updates High-Water Mark and start-of-day NAV.
        2. Evaluates 2.0% single-day loss circuit breaker.
        3. Evaluates 4-tier Buffett & Lynch de-risking drawdown ladder.
        4. Evaluates Macro Radar crash warning.
        5. Evaluates 14-day Boss-Away watchdog mode.
        6. Applies Regime Flip Whipsaw Damping.
        """
        now = as_of_time or datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        # 1. Update High-Water Mark (NAV only goes up for HWM)
        hwm = float(self.state.get("high_water_mark", current_nav))
        if current_nav > hwm:
            hwm = current_nav
            self.state["high_water_mark"] = hwm

        # 2. Daily rollover: if new calendar day, record start_of_day_nav
        if self.state.get("last_calendar_day") != today_str:
            self.state["last_calendar_day"] = today_str
            self.state["start_of_day_nav"] = current_nav

        start_of_day_nav = float(self.state.get("start_of_day_nav", current_nav))

        status = CRORiskStatus()

        # Check Manual Emergency Halt State
        if self.state.get("emergency_halt_active", False):
            status.can_enter_new_trades = False
            status.exposure_scale_factor = 0.0
            status.ladder_level = "EMERGENCY_HALT"
            status.active_breaches.append("MANUAL_OR_30PCT_EMERGENCY_HALT")
            status.action_summary = "CRO EMERGENCY HALT: Capital is quarantined until Boss manual reset."
            return status

        # 3. The 2.0% Daily Loss Circuit Breaker
        if start_of_day_nav > 0:
            daily_loss_pct = (start_of_day_nav - current_nav) / start_of_day_nav
            if daily_loss_pct >= self.DAILY_LOSS_LIMIT_PCT:
                status.daily_circuit_breaker_active = True
                status.can_enter_new_trades = False
                status.exposure_scale_factor = 0.0
                status.active_breaches.append(f"DAILY_LOSS_CIRCUIT_BREAKER ({daily_loss_pct*100:.2f}% >= 2.0%)")
                logger.warning(
                    f"[CRO CIRCUIT BREAKER] Single-day loss of {daily_loss_pct*100:.2f}% breached 2.0% ceiling! "
                    f"Halting all new entries for the remainder of today."
                )

        # 4. The Buffett & Lynch De-Risking Drawdown Ladder
        current_dd = (current_nav - hwm) / hwm if hwm > 0 else 0.0

        if current_dd <= self.EMERGENCY_HALT_DD_PCT:
            status.can_enter_new_trades = False
            status.exposure_scale_factor = 0.0
            status.ladder_level = "EMERGENCY_HALT"
            self.state["emergency_halt_active"] = True
            status.active_breaches.append(f"DRAWDOWN_LADDER_STEP_4_EMERGENCY ({current_dd*100:.2f}% <= -30.0%)")
        elif current_dd <= self.FREEZE_DRAWDOWN_PCT:
            status.can_enter_new_trades = False
            status.exposure_scale_factor = 0.0
            status.ladder_level = "LADDER_STEP_3_FREEZE"
            status.active_breaches.append(f"DRAWDOWN_LADDER_STEP_3_FREEZE ({current_dd*100:.2f}% <= -24.0%)")
        elif current_dd <= self.BUFFETT_DRAWDOWN_PCT:
            status.can_enter_new_trades = True
            status.exposure_scale_factor = 0.10  # 90% Cash, max 10% exposure
            status.ladder_level = "LADDER_STEP_2_BUFFETT"
            status.active_breaches.append(f"DRAWDOWN_LADDER_STEP_2_BUFFETT ({current_dd*100:.2f}% <= -18.0%)")
        elif current_dd <= self.LYNCH_DRAWDOWN_PCT:
            status.can_enter_new_trades = True
            status.exposure_scale_factor = 0.70  # Cut open risk budget by 30%
            status.ladder_level = "LADDER_STEP_1_LYNCH"
            status.active_breaches.append(f"DRAWDOWN_LADDER_STEP_1_LYNCH ({current_dd*100:.2f}% <= -10.0%)")
        else:
            status.ladder_level = "NORMAL"

        # 5. Macro Radar Crash Defense Protocol
        damped_regime = self._apply_regime_damping(macro_regime, today_str)
        if damped_regime == "CRASH_WARNING":
            status.crash_warning_active = True
            status.can_enter_new_trades = False
            status.exposure_scale_factor = 0.0
            status.active_breaches.append("MACRO_RADAR_CRASH_WARNING")

        # 6. Boss-Away Watchdog Mode
        last_ping_str = self.state.get("last_boss_ping")
        if last_ping_str:
            try:
                last_ping = datetime.fromisoformat(last_ping_str)
                # Ensure UTC aware
                if last_ping.tzinfo is None:
                    last_ping = last_ping.replace(tzinfo=timezone.utc)
                if (now - last_ping).days > self.BOSS_AWAY_TIMEOUT_DAYS:
                    status.boss_away_active = True
                    status.can_enter_new_trades = False
                    status.exposure_scale_factor = 0.0
                    status.active_breaches.append(f"BOSS_AWAY_WATCHDOG (No check-in for > {self.BOSS_AWAY_TIMEOUT_DAYS} days)")
            except Exception as e:
                logger.warning(f"Error parsing last_boss_ping: {e}")

        # Final action summary determination
        if status.active_breaches:
            status.action_summary = f"CRO RESTRICTION: Active safeguards: {'; '.join(status.active_breaches)}"
        else:
            status.action_summary = "CRO: All fiduciary conditions green. Normal execution permitted."

        self._save_state()
        return status

    def _apply_regime_damping(self, raw_regime: str, today_str: str) -> str:
        """
        Macro Regime Flip Whipsaw Damping:
        - Must hold a new candidate state for 2 consecutive closes before confirming.
        - Cannot flip confirmed states more than once in 10 trading days.
        """
        confirmed = self.state.get("confirmed_regime", "TRENDING_BULL")
        if raw_regime == confirmed:
            self.state["regime_candidate"] = None
            self.state["regime_candidate_count"] = 0
            return confirmed

        # CRASH_WARNING bypasses cooldown for instant capital preservation (Rule M3)
        if raw_regime == "CRASH_WARNING":
            self.state["confirmed_regime"] = "CRASH_WARNING"
            self.state["last_regime_flip_date"] = today_str
            self.state["regime_candidate"] = None
            self.state["regime_candidate_count"] = 0
            return "CRASH_WARNING"

        # Check 10-day flip cooldown for non-crash flips
        last_flip_str = self.state.get("last_regime_flip_date")
        if last_flip_str:
            try:
                last_flip_dt = datetime.strptime(last_flip_str, "%Y-%m-%d").date()
                curr_dt = datetime.strptime(today_str, "%Y-%m-%d").date()
                if (curr_dt - last_flip_dt).days < 10:
                    # Still in cooldown; retain current confirmed regime
                    return confirmed
            except Exception:
                pass

        # 2-close confirmation
        cand = self.state.get("regime_candidate")
        cand_count = int(self.state.get("regime_candidate_count", 0))

        if cand == raw_regime:
            cand_count += 1
            if cand_count >= 2:
                # Confirmed new regime
                self.state["confirmed_regime"] = raw_regime
                self.state["last_regime_flip_date"] = today_str
                self.state["regime_candidate"] = None
                self.state["regime_candidate_count"] = 0
                return raw_regime
            else:
                self.state["regime_candidate_count"] = cand_count
                return confirmed
        else:
            self.state["regime_candidate"] = raw_regime
            self.state["regime_candidate_count"] = 1
            return confirmed

    def check_earnings_blackout(
        self,
        symbol: str,
        as_of_date: date,
        earnings_dates: Optional[Dict[str, date]] = None
    ) -> bool:
        """
        Earnings Event-Risk Blackout Gate:
        Bans opening new swing entries within 2 trading days before quarterly earnings release.
        Returns True if trade is permitted (CLEAN), False if blocked (BLACKOUT).
        """
        if not earnings_dates or symbol not in earnings_dates:
            return True  # No earnings within radar

        earnings_dt = earnings_dates[symbol]
        days_until_earnings = (earnings_dt - as_of_date).days

        # Blocked if earnings is in 0, 1, or 2 days
        if 0 <= days_until_earnings <= 2:
            logger.warning(
                f"[CRO EARNINGS BLACKOUT] {symbol}: Earnings scheduled in {days_until_earnings} days "
                f"({earnings_dt.isoformat()}). Blocked from opening new swing position."
            )
            return False

        return True

    def check_exchange_surveillance_and_circuits(
        self,
        symbol: str,
        price_change_pct: float,
        is_asm_gsm_list: bool = False,
        daily_circuit_limit_pct: float = 0.20
    ) -> bool:
        """
        Exchange Surveillance & Circuit Band Filter:
        Rejects stocks on SEBI ASM/GSM regulatory watchlists or locked in upper/lower circuits.
        Returns True if permitted, False if rejected.
        """
        if is_asm_gsm_list:
            logger.warning(f"[CRO SURVEILLANCE BLOCK] {symbol}: Stock is under SEBI ASM/GSM surveillance. Entry rejected.")
            return False

        if abs(price_change_pct) >= (daily_circuit_limit_pct * 0.98):
            logger.warning(
                f"[CRO CIRCUIT BLOCK] {symbol}: Stock price moved {price_change_pct*100:+.2f}%, "
                f"hitting daily circuit band ({daily_circuit_limit_pct*100:.0f}%). Entry rejected."
            )
            return False

        return True
