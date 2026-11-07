"""
Two-Factor Safety Fuse Against Accidental Live Order Execution.
==============================================================
Fiduciary Mandate:
Even if `ALPACA_LIVE="1"`, `GROWW_LIVE="1"`, or a live broker endpoint is targeted,
live order execution is HARD-BLOCKED and FAILS CLOSED unless a physical, unversioned
secondary confirmation key file exists on disk containing the exact authorized
cryptographic passphrase.

A single environment variable typo or leaked secret can NEVER trigger real live orders.

Security Threat Model & Operational Scope:
------------------------------------------
Because `EXPECTED_FUSE_PHRASE` is defined in plain text within this source code file,
this safety fuse is designed to prevent OPERATIONAL ACCIDENTS, unintended live deployments,
CI/CD misconfigurations, and automated test runs from routing live capital. It does NOT
prevent deliberate operator misuse or malicious actors with write access to the repository
and filesystem.
"""

import os
from typing import Optional
from trading_system.app.common.logger import get_logger

logger = get_logger("LiveSafetyFuse")

LIVE_FUSE_FILENAME = "LIVE_TRADING_CONFIRMATION_FUSE.key"
EXPECTED_FUSE_PHRASE = "I_CONFIRM_LIVE_REAL_CAPITAL_ORDER_EXECUTION"


class LiveExecutionBlockedError(RuntimeError):
    """Raised when an attempt to route live orders is blocked by the safety fuse."""
    pass


def find_fuse_file() -> Optional[str]:
    """Searches standard project directories for the physical safety fuse file."""
    search_dirs = [
        os.getcwd(),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")),
    ]
    for d in search_dirs:
        candidate = os.path.join(d, LIVE_FUSE_FILENAME)
        if os.path.exists(candidate):
            return candidate
    return None


def verify_live_safety_fuse(broker_name: str = "Unknown Broker") -> bool:
    """
    Verifies that the secondary physical confirmation fuse is explicitly present and valid.
    Raises LiveExecutionBlockedError if the fuse is missing, empty, or contains the wrong phrase.
    """
    fuse_path = find_fuse_file()
    if not fuse_path:
        err_msg = (
            f"CRITICAL SAFETY FUSE ENGAGED: Live order routing for {broker_name} was BLOCKED. "
            f"Even though live mode was flagged, the required physical confirmation file "
            f"'{LIVE_FUSE_FILENAME}' was NOT found on disk. "
            f"Execution halted. Zero live orders placed."
        )
        logger.critical(err_msg)
        raise LiveExecutionBlockedError(err_msg)

    try:
        with open(fuse_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        err_msg = f"SAFETY FUSE ERROR: Failed to read fuse file '{fuse_path}': {e}. Failing closed."
        logger.critical(err_msg)
        raise LiveExecutionBlockedError(err_msg) from e

    if content != EXPECTED_FUSE_PHRASE:
        err_msg = (
            f"CRITICAL SAFETY FUSE INVALID: Content of '{fuse_path}' did not match "
            f"the required authorization phrase. Refusing live execution for {broker_name}."
        )
        logger.critical(err_msg)
        raise LiveExecutionBlockedError(err_msg)

    logger.warning(f"SAFETY FUSE TRIPPED: Live order execution authorized for {broker_name} via {fuse_path}.")
    return True
