import os
import json
from typing import Optional, Dict, Any

class StopLossManager:
    """
    Manages persistent bot & user-overridden stop-loss thresholds per position.
    Stores configurations in a JSON file to sync across Quant Bot & Dashboard UI.
    """
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "stop_loss_config.json")
        self.config_path = config_path
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.global_default_pct = float(data.get("global_default_pct", -0.08))
                    self.overrides: Dict[str, float] = data.get("overrides", {})
            except Exception:
                self.global_default_pct = -0.08
                self.overrides = {}
        else:
            self.global_default_pct = -0.08
            self.overrides = {}

    def _save(self):
        try:
            data = {
                "global_default_pct": self.global_default_pct,
                "overrides": self.overrides
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving stop loss config: {e}")

    def get_stop_loss_pct(self, symbol: str) -> float:
        """Returns stop-loss as negative decimal, e.g. -0.08."""
        sym = symbol.upper()
        return float(self.overrides.get(sym, self.global_default_pct))

    def is_custom_override(self, symbol: str) -> bool:
        """Checks if ticker has an active user manual override."""
        return symbol.upper() in self.overrides

    def has_override(self, symbol: str) -> bool:
        """Alias for is_custom_override."""
        return self.is_custom_override(symbol)

    def get_global_default_pct(self) -> float:
        """Returns the bot global default stop loss percentage."""
        return self.global_default_pct

    def set_stop_loss_pct(self, symbol: str, pct: float):
        """Sets stop-loss for symbol. Converts positive inputs to negative decimal (e.g. 5.0 -> -0.05)."""
        val = float(pct)
        if abs(val) > 1.0:
            val = val / 100.0
        val = -abs(val)
        self.overrides[symbol.upper()] = round(val, 4)
        self._save()

    def reset_stop_loss(self, symbol: str):
        """Reverts stop-loss for symbol back to bot global default."""
        sym = symbol.upper()
        if sym in self.overrides:
            del self.overrides[sym]
            self._save()

    def set_global_default_pct(self, pct: float):
        """Sets bot global default stop loss percentage."""
        val = float(pct)
        if abs(val) > 1.0:
            val = val / 100.0
        self.global_default_pct = round(-abs(val), 4)
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
