"""
Point-in-Time (PIT) Index Constituent Manager
Tracks historical index membership additions, removals, and active constituent sets
to prevent survivorship bias and lookahead bias in quantitative backtesting and live operations.
"""

import os
from typing import Set, Dict, List, Tuple, Optional
import pandas as pd
from trading_system.app.common.logger import get_logger

logger = get_logger("PITConstituentManager")


class PointInTimeConstituentManager:
    """
    Provides strict point-in-time constituent membership for index universes (e.g. S&P 500).
    Ensures that:
      1. Tickers are NEVER traded before their official inclusion date.
      2. Tickers are flagged for mandatory liquidation when excluded / removed.
      3. Symbol representations (e.g., BRK.B vs BRK-B) are cleanly normalized.
    """

    def __init__(
        self,
        changes_csv_path: Optional[str] = None,
        start_end_csv_path: Optional[str] = None,
    ):
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data")
        )
        self.changes_csv_path = changes_csv_path or os.path.join(
            base_dir, "sp500_historical_components_changes.csv"
        )
        self.start_end_csv_path = start_end_csv_path or os.path.join(
            base_dir, "sp500_ticker_start_end.csv"
        )

        self._change_dates: List[pd.Timestamp] = []
        self._date_to_constituents: Dict[pd.Timestamp, Set[str]] = {}
        self._ticker_intervals: Dict[str, List[Tuple[pd.Timestamp, Optional[pd.Timestamp]]]] = {}
        self._is_loaded = False

        self._load_datasets()

    @staticmethod
    def normalize_symbol(sym: str) -> str:
        """Normalizes symbol to standard hyphen format used across Yahoo Finance and broker feeds."""
        return sym.strip().upper().replace(".", "-")

    def _load_datasets(self):
        if not os.path.exists(self.changes_csv_path):
            logger.warning(f"Changes dataset not found at {self.changes_csv_path}")
            return

        # 1. Load Changes CSV
        df_changes = pd.read_csv(self.changes_csv_path)
        df_changes["date"] = pd.to_datetime(df_changes["date"])
        df_changes = df_changes.sort_values("date").reset_index(drop=True)

        for _, row in df_changes.iterrows():
            dt = row["date"]
            raw_tickers = str(row["tickers"]).split(",")
            norm_set = {self.normalize_symbol(t) for t in raw_tickers if t.strip()}
            self._change_dates.append(dt)
            self._date_to_constituents[dt] = norm_set

        # 2. Load Start/End intervals if available
        if os.path.exists(self.start_end_csv_path):
            df_se = pd.read_csv(self.start_end_csv_path)
            for _, row in df_se.iterrows():
                sym = self.normalize_symbol(str(row["ticker"]))
                s_dt = pd.to_datetime(row["start_date"])
                e_dt = pd.to_datetime(row["end_date"]) if pd.notnull(row["end_date"]) else None
                if sym not in self._ticker_intervals:
                    self._ticker_intervals[sym] = []
                self._ticker_intervals[sym].append((s_dt, e_dt))

        self._is_loaded = True
        logger.info(
            f"Loaded PIT Constituents: {len(self._change_dates)} historical changes, {len(self._ticker_intervals)} tracked intervals."
        )

    def get_active_constituents(self, date: pd.Timestamp) -> Set[str]:
        """
        Returns the exact set of active constituent tickers on `date`.
        Uses binary search over historical change events.
        """
        if not self._is_loaded or not self._change_dates:
            return set()

        ts = pd.to_datetime(date)
        # Find latest change event <= ts
        dates_series = pd.Series(self._change_dates)
        idx = dates_series.searchsorted(ts, side="right") - 1
        if idx < 0:
            return set()
        matched_date = self._change_dates[idx]
        return self._date_to_constituents.get(matched_date, set())

    def is_constituent(self, symbol: str, date: pd.Timestamp) -> bool:
        """Checks whether `symbol` was an active index constituent on `date`."""
        norm_sym = self.normalize_symbol(symbol)
        active = self.get_active_constituents(date)
        return norm_sym in active

    def get_membership_intervals(
        self, symbol: str
    ) -> List[Tuple[pd.Timestamp, Optional[pd.Timestamp]]]:
        """Returns the start and end dates of index membership for `symbol`."""
        norm_sym = self.normalize_symbol(symbol)
        return self._ticker_intervals.get(norm_sym, [])
