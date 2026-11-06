"""
Institutional Trial Logger & Overfitting Defense
================================================
Enforces Bailey & López de Prado (2014) anti-overfitting protocol:
1. Tracks every backtest parameter iteration with commit hash, script, universe,
   Kelly fraction, lookback, CAGR, and drawdown.
2. Prevents the tuning loop from fooling itself by logging trial count for Deflated Sharpe Ratio calculation.
3. Guards the 12-month out-of-sample holdout window, logging every time it is opened for promotion.
"""

import os
import sys
import subprocess
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

CANONICAL_LOG_PATH = os.path.join(PROJECT_ROOT, "trading_system", "data", "trial_log.csv")

CSV_COLUMNS = [
    "date",
    "commit_hash",
    "script",
    "universe",
    "kelly_fraction",
    "lookback_days",
    "cagr_pct",
    "max_drawdown_pct",
    "sharpe_ratio",
    "is_holdout_opened",
    "notes"
]


def get_current_commit_hash() -> str:
    """Retrieve current git commit hash, falling back to 'unknown' if git fails."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def initialize_trial_log(log_path: str = CANONICAL_LOG_PATH) -> None:
    """Ensure trial log file exists with proper CSV header."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        df = pd.DataFrame(columns=CSV_COLUMNS)
        df.to_csv(log_path, index=False)


def log_trial(
    cagr_pct: float,
    max_drawdown_pct: float,
    sharpe_ratio: float,
    kelly_fraction: float = 0.40,
    lookback_days: int = 90,
    is_holdout_opened: bool = False,
    commit_hash: Optional[str] = None,
    script: Optional[str] = None,
    universe: Optional[str] = None,
    notes: str = "",
    target_paths: Optional[list] = None
) -> Dict[str, Any]:
    """
    Appends a new trial row to the canonical trial log (trading_system/data/trial_log.csv).
    Automatically captures caller script name and trading universe to prevent cross-run ambiguity.
    """
    if commit_hash is None:
        commit_hash = get_current_commit_hash()

    if script is None:
        try:
            script = os.path.basename(sys.argv[0]) if (sys.argv and sys.argv[0]) else "unknown"
        except Exception:
            script = "unknown"

    if universe is None:
        script_lower = (script or "").lower()
        if "nse" in script_lower or "nifty" in script_lower:
            universe = "NSE_NIFTY50"
        elif "multi_pod" in script_lower or "sp500" in script_lower:
            universe = "US_SP500"
        else:
            universe = "GLOBAL"

    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "commit_hash": commit_hash,
        "script": str(script),
        "universe": str(universe),
        "kelly_fraction": round(float(kelly_fraction), 4),
        "lookback_days": int(lookback_days),
        "cagr_pct": round(float(cagr_pct), 2),
        "max_drawdown_pct": round(float(max_drawdown_pct), 2),
        "sharpe_ratio": round(float(sharpe_ratio), 2),
        "is_holdout_opened": bool(is_holdout_opened),
        "notes": str(notes)
    }

    paths = target_paths or [CANONICAL_LOG_PATH]
    for path in paths:
        initialize_trial_log(path)
        try:
            existing_df = pd.read_csv(path, nrows=0)
            existing_cols = list(existing_df.columns)
            row_dict = {col: entry.get(col, "") for col in existing_cols}
            df_row = pd.DataFrame([row_dict])
            df_row.to_csv(path, mode="a", header=False, index=False)
        except Exception:
            df_row = pd.DataFrame([entry])
            df_row.to_csv(path, mode="a", header=False, index=False)

    return entry


def get_trial_count(log_path: Optional[str] = None) -> int:
    """Read the number of logged trials."""
    path = log_path or CANONICAL_LOG_PATH
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            df = pd.read_csv(path)
            return max(1, len(df))
        except Exception:
            pass
    return 1


def get_trial_log_df(log_path: Optional[str] = None) -> pd.DataFrame:
    """Load the trial log as a DataFrame."""
    path = log_path or CANONICAL_LOG_PATH
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=CSV_COLUMNS)
