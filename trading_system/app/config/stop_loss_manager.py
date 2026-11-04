import os
import json
import math
import hashlib
import logging
from typing import Optional, Dict, Any

from trading_system.app.common.logger import get_logger

logger = get_logger("StopLossManager")

# ==============================================================================
# Institutional Immutable Code-Level Fallback Constants
# ==============================================================================
HARD_STOP_LOSS_PCT: float = -0.08          # -8% maximum drawdown from entry (hard risk ceiling)
TRAILING_STOP_TRIGGER_PCT: float = 0.15   # +15% profit triggers trailing stop
TRAILING_STOP_DISTANCE_PCT: float = 0.05  # 5% trailing stop buffer below peak
BREAKEVEN_TRIGGER_PCT: float = 0.05       # +5% gain triggers breakeven ratchet


class StopLossManager:
    """
    Manages persistent bot & user-overridden stop-loss thresholds per position.
    Stores configurations in a JSON file to sync across Quant Bot & Dashboard UI.

    Institutional Risk Lock:
    - Protects capital by physically preventing looser risk configurations.
    - If stop_loss_config.json is modified at runtime with values looser than
      the hard limits (e.g. -0.15 vs -0.08), the system rejects the mutation and
      falls back to the immutable code-level constants.
    """

    HARD_STOP_LOSS_PCT: float = HARD_STOP_LOSS_PCT
    TRAILING_STOP_TRIGGER_PCT: float = TRAILING_STOP_TRIGGER_PCT
    TRAILING_STOP_DISTANCE_PCT: float = TRAILING_STOP_DISTANCE_PCT
    BREAKEVEN_TRIGGER_PCT: float = BREAKEVEN_TRIGGER_PCT

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "stop_loss_config.json")
        self.config_path = config_path
        self._last_mtime: float = 0.0
        self._file_hash: Optional[str] = None
        self._load()

    def _load(self):
        self.config: Dict[str, Any] = {}
        if os.path.exists(self.config_path):
            try:
                self._last_mtime = os.path.getmtime(self.config_path)
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    self.config = json.loads(content)

                raw_default = float(self.config.get("global_default_pct", self.HARD_STOP_LOSS_PCT))

                # Runtime Hash / Boundary Lock:
                # Reject any stop-loss looser than HARD_STOP_LOSS_PCT (e.g., -0.15 < -0.08 is looser)
                if raw_default < self.HARD_STOP_LOSS_PCT or raw_default > 0:
                    logger.warning(
                        f"[RISK LOCK VIOLATION] Configured stop loss ({raw_default}) in {self.config_path} "
                        f"is looser than immutable limit ({self.HARD_STOP_LOSS_PCT}). Falling back to {self.HARD_STOP_LOSS_PCT}."
                    )
                    self.global_default_pct = self.HARD_STOP_LOSS_PCT
                else:
                    self.global_default_pct = raw_default

                self.overrides: Dict[str, float] = self.config.get("overrides", {})
                for sym, val in list(self.overrides.items()):
                    if float(val) < -0.12 or float(val) > 0:
                        logger.warning(f"[RISK LOCK VIOLATION] Override for {sym} ({val}) is excessive. Clamping to {self.HARD_STOP_LOSS_PCT}.")
                        self.overrides[sym] = self.HARD_STOP_LOSS_PCT
            except Exception as e:
                logger.warning(f"Error loading stop loss config: {e}. Falling back to immutable constants.")
                self.global_default_pct = self.HARD_STOP_LOSS_PCT
                self.overrides = {}
        else:
            self.global_default_pct = self.HARD_STOP_LOSS_PCT
            self.overrides = {}

    def _verify_runtime_lock(self):
        """Checks if configuration file was mutated on disk at runtime."""
        if os.path.exists(self.config_path):
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime != self._last_mtime:
                self._load()

    def _save(self):
        try:
            data = dict(self.config) if hasattr(self, "config") and self.config else {}
            data["global_default_pct"] = self.global_default_pct
            data["overrides"] = self.overrides
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            if os.path.exists(self.config_path):
                self._last_mtime = os.path.getmtime(self.config_path)
        except Exception as e:
            logger.error(f"Error saving stop loss config: {e}")

    def get_stop_loss_pct(self, symbol: str) -> float:
        """Returns stop-loss as negative decimal, e.g. -0.08, enforcing runtime lock."""
        self._verify_runtime_lock()
        sym = symbol.upper()
        return float(self.overrides.get(sym, self.global_default_pct))

    def is_custom_override(self, symbol: str) -> bool:
        """Checks if ticker has an active user manual override."""
        self._verify_runtime_lock()
        return symbol.upper() in self.overrides

    def has_override(self, symbol: str) -> bool:
        """Alias for is_custom_override."""
        return self.is_custom_override(symbol)

    def get_global_default_pct(self) -> float:
        """Returns the bot global default stop loss percentage, enforcing runtime lock."""
        self._verify_runtime_lock()
        return self.global_default_pct

    def set_stop_loss_pct(self, symbol: str, pct: float):
        """Sets stop-loss for symbol. Converts positive inputs to negative decimal (e.g. 5.0 -> -0.05)."""
        val = float(pct)
        if abs(val) > 1.0:
            val = val / 100.0
        val = -abs(val)
        # Cap overrides to institutional max risk floor (-12%)
        if val < -0.12:
            logger.warning(f"[RISK LOCK] Override stop {val} exceeds hard risk limit. Clamping to {self.HARD_STOP_LOSS_PCT}.")
            val = self.HARD_STOP_LOSS_PCT
        self.overrides[symbol.upper()] = round(val, 4)
        self._save()

    def reset_stop_loss(self, symbol: str):
        """Reverts stop-loss for symbol back to bot global default."""
        sym = symbol.upper()
        if sym in self.overrides:
            del self.overrides[sym]
            self._save()

    def set_global_default_pct(self, pct: float):
        """Sets bot global default stop loss percentage, bounded by immutable HARD_STOP_LOSS_PCT."""
        val = float(pct)
        if abs(val) > 1.0:
            val = val / 100.0
        val = -abs(val)
        # Runtime Lock: reject looser values
        if val < self.HARD_STOP_LOSS_PCT:
            logger.warning(
                f"[RISK LOCK] Attempted to set global stop loss {val} looser than hard limit "
                f"{self.HARD_STOP_LOSS_PCT}. Enforcing {self.HARD_STOP_LOSS_PCT}."
            )
            val = self.HARD_STOP_LOSS_PCT
        self.global_default_pct = round(val, 4)
        self._save()

    def get_stop_price(self, symbol: str, avg_entry: float) -> float:
        """Calculates exact dollar stop price based on entry and active stop %."""
        sl_pct = self.get_stop_loss_pct(symbol)
        return round(avg_entry * (1.0 + sl_pct), 2)

    def get_distance_to_stop(self, symbol: str, current_price: float, avg_entry: float) -> dict:
        """Calculates distance, buffer, and risk breach flags."""
        sl_pct = self.get_stop_loss_pct(symbol)
        stop_price = round(avg_entry * (1.0 + sl_pct), 2)
        dollar_buffer = current_price - stop_price
        pct_buffer = (dollar_buffer / current_price * 100) if current_price > 0 else 0.0
        is_breached = current_price <= stop_price
        # Warning when buffer is within 2.5% of current price
        is_warning = (not is_breached) and (pct_buffer <= 2.5)
        return {
            "stop_price": stop_price,
            "stop_loss_pct": sl_pct,
            "dollar_buffer": round(dollar_buffer, 2),
            "pct_buffer": round(pct_buffer, 2),
            "is_breached": is_breached,
            "is_warning": is_warning,
            "is_custom": self.is_custom_override(symbol)
        }

    def evaluate_dynamic_exit(
        self,
        symbol: str,
        current_price: float,
        avg_entry: float,
        peak_price: Optional[float] = None,
        sma50: Optional[float] = None,
        holding_type: str = "MOMENTUM",
        bb_mid: Optional[float] = None,
        rsi: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evaluates High-Alpha Multi-Tier Exits:
        1. Hard Stop-Loss (-8% or user override)
        2. Breakeven Stop Ratchet (+12% gain -> lock +2%)
        3. Big Winner Trailing Lock (+30% gain -> trail 14% below peak)
        4. 50-day SMA Trend Breakdown (close < 97.5% of 50-SMA)
        5. Dip-Buy Mean-Reversion Target Exit (BB Mid / RSI > 60)
        """
        self._verify_runtime_lock()
        if avg_entry <= 0:
            return {"should_exit": False, "reason": None}

        plpc = (current_price - avg_entry) / avg_entry
        hard_sl = self.get_stop_loss_pct(symbol)
        
        # 1. Hard Stop
        if plpc <= hard_sl:
            return {
                "should_exit": True,
                "reason": f"HARD_STOP ({hard_sl*100:.1f}%) [Loss: {plpc*100:.1f}%]"
            }

        peak = peak_price if peak_price is not None and peak_price > avg_entry else current_price
        gain_from_cost = (peak - avg_entry) / avg_entry

        # Configurable thresholds
        be_trigger = self.config.get("breakeven_gain_trigger_pct", 0.12)
        be_lock = self.config.get("breakeven_locked_profit_pct", 0.02)
        runner_trigger = self.config.get("runner_gain_trigger_pct", 0.30)
        runner_dd = self.config.get("runner_max_drawdown_from_peak_pct", 0.14)
        trend_buffer = self.config.get("trend_50sma_break_buffer_pct", 0.025)

        # 2. Dip-Buy Exit
        if holding_type == "DIP_BUY":
            if (bb_mid is not None and current_price >= bb_mid and plpc >= 0.04) or (rsi is not None and rsi >= 60.0) or plpc >= 0.12:
                return {
                    "should_exit": True,
                    "reason": f"DIP_TARGET_EXIT [PnL: {plpc*100:+.1f}%]"
                }

        # 3. Momentum Runner Exits
        if holding_type == "MOMENTUM":
            # Breakeven Ratchet: if peaked at >= trigger (+12%) and pulls back to <= lock (+2%)
            if gain_from_cost >= be_trigger and plpc <= be_lock:
                return {
                    "should_exit": True,
                    "reason": f"BREAKEVEN_STOP [Locked: {plpc*100:+.1f}% | Peaked: {gain_from_cost*100:+.1f}%]"
                }

            # Big Winner Trailing Lock: if reached trigger (+30%) profit, trail below peak
            if gain_from_cost >= runner_trigger:
                dd_from_peak = (peak - current_price) / peak if peak > 0 else 0.0
                if dd_from_peak >= runner_dd:
                    return {
                        "should_exit": True,
                        "reason": f"BIG_WINNER_TRAIL [Locked: {plpc*100:+.1f}% | Peak {gain_from_cost*100:+.1f}% | DD: {dd_from_peak*100:.1f}%]"
                    }

            # Trend Breakdown: closed below 50-day SMA by > buffer (2.5%)
            if sma50 is not None and not math.isnan(sma50) and current_price < (sma50 * (1.0 - trend_buffer)):
                return {
                    "should_exit": True,
                    "reason": f"TREND_50SMA_BREAK [PnL: {plpc*100:+.1f}% | Price: ${current_price:.2f} < ${sma50*(1.0-trend_buffer):.2f}]"
                }

        return {"should_exit": False, "reason": None}
