"""Multi-Bot Trading System: Specialist Pods / Execution Bots."""

from trading_system.app.bots.etf_gold_bot import ETFGoldsStrategy, ETFGoldsPaperRunner
from trading_system.app.bots.bond_cash_bot import (
    BondCashB0Strategy,
    BondCashB1Strategy,
    BondCashB2Strategy,
    BondCashPaperRunner
)

__all__ = [
    "ETFGoldsStrategy",
    "ETFGoldsPaperRunner",
    "BondCashB0Strategy",
    "BondCashB1Strategy",
    "BondCashB2Strategy",
    "BondCashPaperRunner",
]
