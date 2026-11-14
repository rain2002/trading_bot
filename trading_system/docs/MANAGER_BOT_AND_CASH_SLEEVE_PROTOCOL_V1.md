# Phase 2 Protocol: Manager Bot and Cash Sleeve

**Date**: Nov 13, 2026  
**Author**: @Raja Nithin  
**Document ID**: `PROTOCOL-MANAGER-BOT-CASH-SLEEVE-V1-20261113`  
**Classification**: Institutional Pre-Registration Document (Phase 2 Governance)  
**Status**: PRE-REGISTERED (LOCKED PRIOR TO CODE EXECUTION)  

---

## 1. Mandate and Scope

The manager bot decides how much capital each trading bot may use and cuts risk when the whole portfolio is losing. It never predicts markets, picks stocks or overrides a bot's own signals. With only the ETF bot cleared for paper trading, Phase 2 is deliberately small: one bot plus a cash sleeve, built so later bots plug in without changes.

### In Scope
- Capital split between bots and the cash sleeve, with fixed target shares set by you.
- A portfolio-level drawdown throttle and a hard kill switch.
- Unitized NAV accounting, so lump sums and SIP top-ups don't distort returns.
- Daily reconciliation of the manager's NAV against the sum of the bots' NAVs.

### Out of Scope for Phase 2
- Any market-evaluation or regime signal. It enters at Phase 5 only if it beats fixed weights out of sample.
- Any bot with an uncleared gate holding real capital. Such bots stay on paper with zero real share.
- F&O, intraday trading and live orders.

**Cash sleeve**: `LIQUIDBEES.NS` only. The retreat sleeve carries no duration risk, unlike the 20% gilt holding inside the ETF champion, which stays as specified in Amendment V1.1.

**Authority**: The manager may act on its own only to reduce risk. Anything that raises risk, changes weights or moves a bot from paper to live waits for the monthly window and your yes.

---

## 2. Manager Rules

All thresholds are measured on the manager's unitized NAV against its high-water mark, which never resets, so top-ups and withdrawals can't fake a recovery or a loss. Your drawdown tolerance is -45%, so the kill switch sits at -40%.

| Rule | Setting | Why |
| :--- | :--- | :--- |
| **Target shares** | ETF bot 100% of deployable capital; any later bot gets 0% real until its gate clears, then the share you approve | Only the ETF bot has evidence |
| **Rebalance between bots** | Monthly check, trade only if a share drifts more than 5 points from target | Keeps turnover low |
| **Throttle level 1** | NAV drawdown worse than -15%: risk assets held at 50% of target, rest to `LIQUIDBEES.NS` | First defence, well inside -45% |
| **Throttle level 2** | Drawdown worse than -30%: risk assets at 25% of target | Second defence |
| **Kill switch** | Drawdown worse than -40%: everything to `LIQUIDBEES.NS`, no restart without your yes | Hard stop before the -45% limit |
| **Re-risking** | Move up one level only after drawdown is 5 points better than that level's trigger for 21 trading days | Avoids whipsaw and the old high-water-mark deadlock |
| **Top-ups and SIP** | New money buys units at the current unit value and goes to the most underweight sleeve; no selling to make room | Clean accounting, no forced sales |
| **Reconciliation** | Daily check that manager NAV equals the sum of bot NAVs within 0.1%; a larger gap pauses all trading | Catches state bugs early |

> [!NOTE]
> The throttle is a hypothesis, not a given. The ETF bot's trend-and-throttle candidate gave up return for lower drawdown, so the manager's throttle must prove itself in the tests below. If it doesn't, the manager ships with fixed shares and the kill switch only.

---

## 3. Pre-Registered Tests, Hurdles and Gate B

The manager makes a risk claim, not an alpha claim, so it is judged on drawdown cost and benefit rather than a Deflated Sharpe Ratio. The trial family is declared up front: exactly the two variants in test T1, so $N = 2$. Any further variant is logged and raises $N$.

| Test | What it runs | Pass condition |
| :--- | :--- | :--- |
| **T1 Throttle value** | Manager with throttle against manager with fixed shares plus kill switch, on the ETF champion's equity curves: 2007–2024 index proxies and the 2025–26 real-ETF holdout (already opened, so labelled as seen) | Throttle cuts max drawdown by at least 20% (relative), costs at most 1.0 point of CAGR, and does not lower Sharpe. Otherwise ship fixed shares plus kill switch |
| **T2 Accounting** | Random lump sums and SIP top-ups through unitized NAV, checked against an independent money-weighted calculation | Unit value matches within 0.01% on every date |
| **T3 Kill switch** | Inject a -41% NAV path on paper | All capital moves to `LIQUIDBEES.NS` in one cycle, status flips to halted, no automatic restart |
| **T4 Reconciliation** | Break a bot's state file on purpose | Gap above 0.1% pauses all trading and raises an alert |
| **T5 Re-risking** | Replay a drawdown and recovery path | Moves up one level only after the 21-day condition, never skips a level |

*Note on T1*: T1 has low statistical power: the champion's history holds only a few drawdown episodes, mainly 2008 and 2020. A pass is weak evidence and a fail is also weak. The rule above—ship the simpler fixed version unless the throttle clearly earns its place—handles that.

### Gate B for the Manager (13 Weeks of Paper, run alongside the ETF Bot's)
- Daily reconciliation within 0.1% on at least 95% of NSE trading days, with every gap explained.
- Tests T3 and T4 each passed once in the live paper workflow, not only in unit tests.
- The workflow runs on at least 95% of weekdays with no manual fix to state.
- No live orders at any point.

---

## 4. Interface, Code Checklist and Decisions

Every bot reports to the manager through one shared shape, so adding the S&P 500 or NSE bots later changes configuration, not code:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd

@dataclass
class BotReport:
    nav: float            # bot NAV in INR, from its own state
    risk_status: Dict[str, Any]
    gate_status: str      # NONE, GATE_A, GATE_B_PAPER, LIVE_APPROVED
    last_update: pd.Timestamp
    stale: bool           # True if older than one NSE trading day

class ManagerInterface(ABC):
    @abstractmethod
    def evaluate_shares(
        self,
        as_of: pd.Timestamp,
        reports: Dict[str, BotReport],
        nav_state: Dict[str, Any]
    ) -> Dict[str, float]:
        """Target capital share per bot plus the cash sleeve, summing to 1.0.
        A bot whose gate_status is below LIVE_APPROVED gets 0.0 real share.
        A stale report freezes that bot's share and raises an alert."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Throttle level, drawdown, halted flag, last reconciliation gap."""
        pass
```

### Build Order (You Code, I Review Each Commit)
1. This protocol committed alone, with its SHA-256, before any code.
2. Unitized NAV and its test T2.
3. Throttle, kill switch and re-risking logic with tests T3, T4 and T5.
4. The T1 runner, which logs both variants as trials and states $N = 2$.
5. `run_manager.py`, the manager state files on the `state` branch, and a workflow that runs after the ETF bot's, in the same `trading-state` group, with `permissions: contents: write`.

### Approved Decisions
- [x] **Throttle at -15% and -30%, kill switch at -40%**: Approved.
- [x] **Judge the manager on test T1 with $N = 2$, and no Deflated Sharpe Ratio**: Approved.
- [x] **ETF bot holds 100% of deployable capital, with no separate cash reserve**: Approved.
- [x] **The manager's Gate B runs alongside the ETF bot's, starting once the manager code is merged**: Approved.
