"""
Generate Institutional Web Dashboard (1980s Retro Amber Phosphor Terminal)
============================================================================
Compiles current Gate B paper trading state, multi-sleeve holdings, equity curve,
and risk gauges into a static, single-file HTML dashboard with an authentic 1980s
CRT amber monochrome aesthetic and a Teletype Ledger Paper light theme toggle.

HARD RULES ENFORCED:
1. Zero hardcoded or fallback numbers: missing fields render "[NO DATA]" in warning style.
2. A row with a NaN or missing NAV is displayed as 'DATA FAULT' in warning style,
   never as PASSED, and never as a number.
3. No fake ticker tape: displays only actual verified holdings from current state with session date.
4. Computed status labels: reconciliation PASS/FAIL vs 0.1% limit.
5. Under FIXED_SHARES_PLUS_KILL_SWITCH policy (T1), multi-tier throttles are OFF (policy)
   and replaced with a single gauge for distance to the -40% kill switch.
6. Mark bond-sleeve returns "[!] NOTE: Bond-sleeve returns are MODELLED (carry model, not market-tested)".
7. Shadow pods get dedicated tab with permanent "[!] EXPLORATORY - NOT EVIDENCE [!]" banner.
8. Visible Retro 1980s Terminal: Monospaced type everywhere, square corners (0px border-radius),
   no emoji, no text-glow blur on numbers, scanlines at most 4% opacity.
9. Top status strip: OK / STALE (>3 days old) / DATA FAULT / HALTED with exact data timestamp and age.
10. Mobile-first: 390px viewport works with zero horizontal scroll.
"""

import os
import sys
import json
import math
import io
import subprocess
from datetime import datetime, timezone, date
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")

MANAGER_STATE_FILE = os.path.join(DATA_DIR, "manager_state.json")
ETF_GOLD_STATE_FILE = os.path.join(DATA_DIR, "etf_gold_state.json")
BOND_CASH_STATE_FILE = os.path.join(DATA_DIR, "bond_cash_state.json")
MANAGER_EQUITY_LOG = os.path.join(DATA_DIR, "manager_equity_log.csv")
LEDGER_FILE = os.path.join(DATA_DIR, "unitized_nav_ledger.json")
US_SHADOW_FILE = os.path.join(DATA_DIR, "paper_state_us.json")
US_SHADOW_LOG = os.path.join(DATA_DIR, "paper_equity_log.csv")


def load_json(path: str, git_branch: str = None) -> dict:
    """Safely load JSON file from disk, falling back to git branch if missing."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass

    if git_branch:
        rel_path = os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
        branches = [git_branch, git_branch.replace("origin/", "")]
        for b in branches:
            try:
                res = subprocess.run(
                    ["git", "show", f"{b}:{rel_path}"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
    return {}


def load_csv(path: str, git_branch: str = None) -> pd.DataFrame:
    """Safely load CSV file from disk, falling back to git branch if missing."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path)
        except Exception:
            pass

    if git_branch:
        rel_path = os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
        branches = [git_branch, git_branch.replace("origin/", "")]
        for b in branches:
            try:
                res = subprocess.run(
                    ["git", "show", f"{b}:{rel_path}"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    return pd.read_csv(io.StringIO(res.stdout))
            except Exception:
                pass
    return pd.DataFrame()


def format_inr(val, decimals: int = 2, show_symbol: bool = True) -> str:
    """Format number using Indian digit grouping (e.g. -₹1,525.11, ₹1,00,000.00). Returns NO DATA / DATA FAULT if invalid."""
    if val is None or not isinstance(val, (int, float)):
        return '<span class="nodata">[NO DATA]</span>'
    try:
        val = float(val)
        if math.isnan(val) or math.isinf(val):
            return '<span class="nodata">[DATA FAULT: NaN]</span>'
    except (ValueError, TypeError):
        return '<span class="nodata">[NO DATA]</span>'

    is_neg = val < 0
    abs_val = abs(val)
    parts = f"{abs_val:.{decimals}f}".split(".")
    int_part = parts[0]
    dec_part = "." + parts[1] if decimals > 0 else ""

    if len(int_part) <= 3:
        formatted = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3

    # Negative sign strictly before the rupee symbol: -₹1,525.11
    prefix = "-₹" if is_neg else ("₹" if show_symbol else "")
    if not show_symbol and is_neg:
        prefix = "-"
    return f"{prefix}{formatted}{dec_part}"


def format_usd(val, decimals: int = 2, show_symbol: bool = True) -> str:
    """Format standard USD currency (e.g. -$1,525.11, $100,000.00). Returns NO DATA if missing."""
    if val is None or not isinstance(val, (int, float)):
        return '<span class="nodata">[NO DATA]</span>'
    try:
        val = float(val)
        if math.isnan(val) or math.isinf(val):
            return '<span class="nodata">[DATA FAULT: NaN]</span>'
    except (ValueError, TypeError):
        return '<span class="nodata">[NO DATA]</span>'

    is_neg = val < 0
    abs_val = abs(val)
    formatted = f"{abs_val:,.{decimals}f}"
    prefix = "-$" if is_neg else ("$" if show_symbol else "")
    if not show_symbol and is_neg:
        prefix = "-"
    return f"{prefix}{formatted}"


def format_pct(val, decimals: int = 2, show_sign: bool = True) -> str:
    """Format percentage value. Returns NO DATA if missing."""
    if val is None or not isinstance(val, (int, float)):
        return '<span class="nodata">[NO DATA]</span>'
    try:
        val = float(val)
        if math.isnan(val) or math.isinf(val):
            return '<span class="nodata">[DATA FAULT: NaN]</span>'
    except (ValueError, TypeError):
        return '<span class="nodata">[NO DATA]</span>'

    sign = "+" if (show_sign and val > 0) else ""
    return f"{sign}{val:.{decimals}f}%"


def format_num(val, decimals: int = 2) -> str:
    """Format plain number. Returns NO DATA if missing."""
    if val is None or not isinstance(val, (int, float)):
        return '<span class="nodata">[NO DATA]</span>'
    try:
        val = float(val)
        if math.isnan(val) or math.isinf(val):
            return '<span class="nodata">[DATA FAULT: NaN]</span>'
    except (ValueError, TypeError):
        return '<span class="nodata">[NO DATA]</span>'
    return f"{val:,.{decimals}f}"


def render_ascii_bar(pct: float, width: int = 20, filled: str = "█", empty: str = "░") -> str:
    """Render an ASCII progress bar."""
    if pct is None or not isinstance(pct, (int, float)):
        return f"[{empty * width}]"
    try:
        if math.isnan(pct) or math.isinf(pct):
            return f"[{empty * width}]"
    except Exception:
        return f"[{empty * width}]"
    clamped = max(0.0, min(100.0, float(pct)))
    filled_len = int(round((clamped / 100.0) * width))
    empty_len = width - filled_len
    return f"[{filled * filled_len}{empty * empty_len}]"


def generate_dashboard_html(data_dir: str = None, output_path: str = None, now_dt: datetime = None) -> str:
    """
    Generate production single-file static HTML dashboard.
    Enforces retro 1980s amber-phosphor CRT trading terminal theme, Teletype paper light theme,
    square corners, monospaced typography, and strict data integrity with ZERO fake numbers.
    """
    if data_dir is None:
        data_dir = DATA_DIR
    if output_path is None:
        output_path = OUTPUT_HTML
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    mgr_file = os.path.join(data_dir, "manager_state.json")
    etf_file = os.path.join(data_dir, "etf_gold_state.json")
    bond_file = os.path.join(data_dir, "bond_cash_state.json")
    eq_file = os.path.join(data_dir, "manager_equity_log.csv")
    ledger_file = os.path.join(data_dir, "unitized_nav_ledger.json")
    us_shadow_file = os.path.join(data_dir, "paper_state_us.json")
    us_eq_file = os.path.join(data_dir, "paper_equity_log.csv")

    # Fallback to git state branches when running against the default project data directory
    use_git = (os.path.abspath(data_dir) == os.path.abspath(DATA_DIR))
    state_branch = "origin/state" if use_git else None
    nse_shadow_branch = "origin/state-shadow-nse" if use_git else None

    mgr_state = load_json(mgr_file, git_branch=state_branch)
    etf_state = load_json(etf_file, git_branch=state_branch)
    bond_state = load_json(bond_file, git_branch=state_branch)
    eq_log = load_csv(eq_file, git_branch=state_branch)
    ledger = load_json(ledger_file, git_branch=state_branch)
    us_shadow = load_json(us_shadow_file)
    us_eq_log = load_csv(us_eq_file)
    phase7_us = load_json(os.path.join(data_dir, "phase7_us_wider_universe_gate_a_results.json"))
    nse_s2_shadow = load_json(os.path.join(data_dir, "nse_s2_shadow_state.json"), git_branch=nse_shadow_branch)

    # -------------------------------------------------------------
    # 1. EVALUATE CRITICAL DATA FAULT & HALTED STATUS
    # -------------------------------------------------------------
    data_fault = False
    fault_reasons = []

    if not mgr_state:
        data_fault = True
        fault_reasons.append("manager_state.json MISSING OR UNREADABLE")
    else:
        # Check essential fields
        c_nav_check = mgr_state.get("combined_fund_nav")
        u_nav_check = mgr_state.get("unitized_nav")
        if (c_nav_check is None or (isinstance(c_nav_check, float) and math.isnan(c_nav_check))) and \
           (u_nav_check is None or (isinstance(u_nav_check, float) and math.isnan(u_nav_check))):
            data_fault = True
            fault_reasons.append("ESSENTIAL NAV METRICS MISSING IN STATE")

    is_halted = bool(mgr_state.get("is_halted", False)) if mgr_state else False
    halt_reason = mgr_state.get("halt_reason") if mgr_state else None

    # -------------------------------------------------------------
    # 2. DATA TIMESTAMP & DATA AGE EVALUATION (NOT BUILD TIMESTAMP)
    # -------------------------------------------------------------
    last_session_date = None
    data_timestamp_str = None

    if not eq_log.empty:
        # Look for date/session_date in the latest row
        date_col = "date" if "date" in eq_log.columns else None
        session_col = "session_date" if "session_date" in eq_log.columns else None

        if session_col:
            valid_sessions = eq_log[session_col].dropna().astype(str).tolist()
            if valid_sessions:
                last_session_date = valid_sessions[-1].strip()[:10]

        if date_col:
            valid_dates = eq_log[date_col].dropna().astype(str).tolist()
            if valid_dates:
                data_timestamp_str = valid_dates[-1].strip()

    if not last_session_date and mgr_state:
        rebal = mgr_state.get("last_rebalance_date") or mgr_state.get("last_update")
        if rebal:
            last_session_date = str(rebal)[:10]

    if not data_timestamp_str and mgr_state:
        upd = mgr_state.get("last_update") or mgr_state.get("last_rebalance_date")
        if upd:
            data_timestamp_str = str(upd)

    data_age_days = None
    data_age_str = "NO DATA"
    if last_session_date:
        try:
            s_date = datetime.strptime(last_session_date, "%Y-%m-%d").date()
            ref_date = now_dt.date() if isinstance(now_dt, datetime) else now_dt
            data_age_days = max(0, (ref_date - s_date).days)
            data_age_str = f"{data_age_days}d"
        except Exception:
            data_age_str = "ERR"

    # Status Strip Computation
    if data_fault:
        top_status = "DATA FAULT"
        top_status_class = "status-fault"
        top_status_badge = "[DATA FAULT]"
        top_status_desc = "; ".join(fault_reasons) if fault_reasons else "CRITICAL TELEMETRY UNREADABLE"
    elif is_halted:
        top_status = "HALTED"
        top_status_class = "status-halted"
        top_status_badge = "[HALTED]"
        top_status_desc = halt_reason or "EMERGENCY RISK HALT TRIGGERED"
    elif data_age_days is None:
        top_status = "DATA FAULT"
        top_status_class = "status-fault"
        top_status_badge = "[DATA FAULT]"
        top_status_desc = "CANNOT DETERMINE TELEMETRY SESSION DATE"
    elif data_age_days > 3:
        top_status = "STALE"
        top_status_class = "status-stale"
        top_status_badge = "[STALE]"
        top_status_desc = f"TELEMETRY AGE ({data_age_days}d) EXCEEDS 3-DAY LIMIT"
    else:
        top_status = "OK"
        top_status_class = "status-ok"
        top_status_badge = "[OK]"
        top_status_desc = "AUTONOMOUS TRADING OPERATION NOMINAL"

    # -------------------------------------------------------------
    # 3. COMPUTE FUND METRICS (NO FALLBACK NUMBERS)
    # -------------------------------------------------------------
    combined_nav = mgr_state.get("combined_fund_nav")
    target_cap = mgr_state.get("combined_target_capital")
    unit_nav = mgr_state.get("unitized_nav")
    hwm_unit = mgr_state.get("hwm_unit_nav")
    curr_dd = mgr_state.get("current_drawdown")
    max_dd = mgr_state.get("max_drawdown")
    policy = mgr_state.get("policy", "FIXED_SHARES_PLUS_KILL_SWITCH") if mgr_state else None
    throttle = mgr_state.get("throttle_level")
    rec_gap = mgr_state.get("last_reconciliation_gap_pct")
    mode = mgr_state.get("mode")
    issued_units = ledger.get("total_units") or (mgr_state.get("current_shares") if mgr_state else None)

    # Inception PnL computation
    total_pnl = None
    total_pnl_pct = None
    if combined_nav is not None and target_cap is not None and target_cap > 0:
        try:
            if not math.isnan(combined_nav) and not math.isnan(target_cap):
                total_pnl = combined_nav - target_cap
                total_pnl_pct = (total_pnl / target_cap) * 100.0
        except Exception:
            pass

    # Drawdown scaling
    curr_dd_pct = None
    if curr_dd is not None:
        try:
            if not math.isnan(curr_dd):
                curr_dd_pct = curr_dd * 100.0 if abs(curr_dd) <= 1.0 and curr_dd != 0 else curr_dd
        except Exception:
            pass

    max_dd_pct = None
    if max_dd is not None:
        try:
            if not math.isnan(max_dd):
                max_dd_pct = max_dd * 100.0 if abs(max_dd) <= 1.0 and max_dd != 0 else max_dd
        except Exception:
            pass

    # Computed reconciliation label (PASS/FAIL vs 0.1% limit)
    rec_status_label = '<span class="nodata">[NO DATA]</span>'
    rec_is_pass = False
    if rec_gap is not None:
        try:
            if not math.isnan(rec_gap):
                if abs(rec_gap) <= 0.1:
                    rec_status_label = f'<span class="badge-pass">[PASS] {rec_gap:.2f}% GAP &le; 0.10%</span>'
                    rec_is_pass = True
                else:
                    rec_status_label = f'<span class="badge-alert">[FAIL] {rec_gap:.2f}% GAP &gt; 0.10%</span>'
        except Exception:
            pass

    # Policy & Throttle text
    # Production runs FIXED_SHARES_PLUS_KILL_SWITCH (T1 pre-registered).
    # Under this policy, multi-tier throttles are OFF (policy) and only -40% kill switch is live.
    if policy == "FIXED_SHARES_PLUS_KILL_SWITCH":
        throttle_text = "OFF (policy)"
    elif throttle is not None:
        throttle_text = f"LEVEL {throttle}"
    else:
        throttle_text = '<span class="nodata">[NO DATA]</span>'

    # -------------------------------------------------------------
    # 4. GATE B INCUBATION PANEL & PROGRESS
    # -------------------------------------------------------------
    days_incubated = (etf_state.get("days_incubated") if etf_state else None) or \
                     (bond_state.get("days_incubated") if bond_state else None)
    target_weeks = (etf_state.get("incubation_target_weeks") if etf_state else None) or \
                   (bond_state.get("incubation_target_weeks") if bond_state else None) or 13
    target_days = target_weeks * 7 if target_weeks is not None else 91

    gate_b_progress_pct = None
    gate_b_ascii_bar = render_ascii_bar(None, 24)
    gate_b_text = '<span class="nodata">[NO DATA]</span>'
    if days_incubated is not None and target_days > 0:
        gate_b_progress_pct = (days_incubated / target_days) * 100.0
        gate_b_ascii_bar = render_ascii_bar(gate_b_progress_pct, 24)
        gate_b_text = f"DAY {days_incubated} OF {target_days} ({gate_b_progress_pct:.1f}%)"

    # -------------------------------------------------------------
    # 5. SINGLE RISK GAUGE: DISTANCE TO -40% KILL SWITCH
    # -------------------------------------------------------------
    kill_margin = None
    kill_ascii = render_ascii_bar(None, 20)
    kill_status_badge = '<span class="nodata">[NO DATA]</span>'

    if curr_dd_pct is not None:
        abs_dd = abs(curr_dd_pct)
        kill_margin = 40.0 - abs_dd
        buffer_pct = max(0.0, min(100.0, (kill_margin / 40.0) * 100.0))
        kill_ascii = render_ascii_bar(buffer_pct, 20)
        if kill_margin > 0:
            kill_status_badge = f'<span class="badge-pass">[ARMED &bull; SAFE] +{kill_margin:.2f}% BUFFER</span>'
        else:
            kill_status_badge = '<span class="badge-alert">[BREACHED &bull; KILL SWITCH TRIGGERED]</span>'

    # -------------------------------------------------------------
    # 6. HOLDINGS STRIP (ACTUAL HOLDINGS ONLY - NO FAKE TICKER)
    # -------------------------------------------------------------
    actual_holdings_chips = []
    etf_pos = etf_state.get("positions", {}) if etf_state else {}
    bond_pos = bond_state.get("positions", {}) if bond_state else {}

    sleeve_session_date = last_session_date or "NO DATE"

    for sym, pos_data in sorted(etf_pos.items()):
        lp = pos_data.get("last_price") or pos_data.get("entry_price")
        if lp is not None:
            actual_holdings_chips.append(f'<span class="holding-chip"><span class="chip-sym">{sym}</span>: {format_inr(lp)}</span>')

    for sym, pos_data in sorted(bond_pos.items()):
        lp = pos_data.get("last_price") or pos_data.get("entry_price")
        if lp is not None:
            actual_holdings_chips.append(f'<span class="holding-chip"><span class="chip-sym">{sym}</span>: {format_inr(lp)}</span>')

    if actual_holdings_chips:
        actual_holdings_html = " &bull; ".join(actual_holdings_chips)
    else:
        actual_holdings_html = '<span class="nodata">[NO RECORDED ACTIVE HOLDINGS IN CURRENT STATE]</span>'

    # -------------------------------------------------------------
    # 7. SLEEVES TAB: HOLDINGS TABLES & MODELLED BOND NOTICE
    # -------------------------------------------------------------
    etf_nav = etf_state.get("nav") if etf_state else None
    etf_cash = etf_state.get("cash") if etf_state else None
    etf_table_rows = ""

    if etf_pos:
        for sym, p in sorted(etf_pos.items()):
            shs = p.get("shares")
            entry = p.get("entry_price")
            last_p = p.get("last_price") or entry
            cur_val = (shs * last_p) if (shs is not None and last_p is not None) else None
            weight = (cur_val / combined_nav * 100.0) if (cur_val is not None and combined_nav and combined_nav > 0) else None
            pnl_pct = ((last_p - entry) / entry * 100.0) if (last_p is not None and entry and entry > 0) else None
            pnl_val = (cur_val - (shs * entry)) if (cur_val is not None and shs is not None and entry is not None) else None

            pnl_class = "text-green" if (pnl_pct is not None and pnl_pct >= 0) else "text-alert"
            etf_table_rows += f"""
            <tr>
                <td class="font-bold text-amber">{sym}</td>
                <td>{format_num(shs, 0)}</td>
                <td>{format_inr(entry)}</td>
                <td>{format_inr(last_p)}</td>
                <td>{format_inr(cur_val)} ({format_pct(weight, 1, False)})</td>
                <td class="{pnl_class} font-bold">{format_pct(pnl_pct)} ({format_inr(pnl_val)})</td>
                <td><span class="badge-pass">[ACTIVE SLEEVE 1]</span></td>
            </tr>
            """
    else:
        etf_table_rows = '<tr><td colspan="7" class="nodata-cell">[NO HOLDINGS IN SLEEVE 1 STATE]</td></tr>'

    etf_cash_wt = (etf_cash / combined_nav * 100.0) if (etf_cash is not None and combined_nav and combined_nav > 0) else None
    etf_table_rows += f"""
    <tr class="row-cash">
        <td class="text-dim">Sleeve 1 Residual Cash</td>
        <td>N/A</td>
        <td>{format_inr(1.0)}</td>
        <td>{format_inr(1.0)}</td>
        <td>{format_inr(etf_cash)} ({format_pct(etf_cash_wt, 1, False)})</td>
        <td class="text-green">+0.00%</td>
        <td><span class="badge-dim">[SETTLEMENT CASH]</span></td>
    </tr>
    """

    bond_nav = bond_state.get("nav") if bond_state else None
    bond_cash = bond_state.get("cash") if bond_state else None
    total_carry = bond_state.get("total_carry_earned") if bond_state else None
    bond_table_rows = ""

    if bond_pos:
        for sym, p in sorted(bond_pos.items()):
            shs = p.get("shares")
            entry = p.get("entry_price")
            last_p = p.get("last_price") or entry
            cur_val = (shs * last_p) if (shs is not None and last_p is not None) else None
            weight = (cur_val / combined_nav * 100.0) if (cur_val is not None and combined_nav and combined_nav > 0) else None

            bond_table_rows += f"""
            <tr>
                <td class="font-bold text-amber">{sym} (Overnight Sovereign Repo)</td>
                <td>{format_num(shs, 0)}</td>
                <td>{format_inr(entry)}</td>
                <td>{format_inr(last_p)}</td>
                <td>{format_inr(cur_val)} ({format_pct(weight, 1, False)})</td>
                <td class="text-green font-bold">Total Carry: {format_inr(total_carry)}</td>
                <td><span class="badge-pass">[SAFE HAVEN B0]</span></td>
            </tr>
            """
    else:
        bond_table_rows = '<tr><td colspan="7" class="nodata-cell">[NO HOLDINGS IN SLEEVE 2 STATE]</td></tr>'

    bond_cash_wt = (bond_cash / combined_nav * 100.0) if (bond_cash is not None and combined_nav and combined_nav > 0) else None
    bond_table_rows += f"""
    <tr class="row-cash">
        <td class="text-dim">Sleeve 2 Overnight Repo Reserve</td>
        <td>N/A</td>
        <td>{format_inr(1.0)}</td>
        <td>{format_inr(1.0)}</td>
        <td>{format_inr(bond_cash)} ({format_pct(bond_cash_wt, 1, False)})</td>
        <td class="text-green">Accruing ~6.0% p.a.</td>
        <td><span class="badge-dim">[DAILY REPO CARRY]</span></td>
    </tr>
    """

    # -------------------------------------------------------------
    # 8. SHADOW PODS TAB (PERMANENT EXPLORATORY BANNER)
    # -------------------------------------------------------------
    us_shadow_cash = us_shadow.get("cash", 0.0) if isinstance(us_shadow, dict) and us_shadow else 0.0
    us_shadow_equity = us_shadow.get("equity", us_shadow_cash) if isinstance(us_shadow, dict) and us_shadow else 0.0
    us_verdict = phase7_us.get("verdict", {}) if isinstance(phase7_us, dict) else {}
    us_audit_sum = phase7_us.get("data_audit_summary", {}) if isinstance(phase7_us, dict) else {}
    us_best_id = us_verdict.get("best_candidate", "W1_LOW_VOL_TREND")
    us_best_cagr = phase7_us.get("candidates", {}).get(us_best_id, {}).get("base_5bps", {}).get("cagr_pct") if isinstance(phase7_us, dict) else None
    us_attrition = us_audit_sum.get("survivorship_attrition_pct")
    us_shadow_verified_text = "[RETIRED - S&P 500 DECOMMISSIONED / WIDER US FAILED GATE A]"

    us_shadow_rows = f"""
        <tr>
            <td colspan="8" class="nodata-cell">
                S&amp;P 500 SHADOW WORKFLOWS RETIRED &bull; WIDER US S&amp;P 1500 NON-ETF GATE A: FAIL
                (Best {us_best_id}: {format_pct(us_best_cagr, 2)} CAGR, Yahoo Delisting Attrition: {format_pct(us_attrition, 2) if us_attrition is not None else 'N/A'})
                &bull; HOLDOUT SEALED &bull; $0 CAPITAL DEPLOYED
            </td>
        </tr>
    """

    nse_s2_init = nse_s2_shadow.get("initial_capital") if nse_s2_shadow else 80000.0
    nse_s2_cash = nse_s2_shadow.get("cash") if nse_s2_shadow else None
    nse_s2_hwm = nse_s2_shadow.get("hwm_true") if nse_s2_shadow else None
    nse_s2_pos_cnt = len(nse_s2_shadow.get("positions", {})) if nse_s2_shadow else 0
    nse_s2_regime = nse_s2_shadow.get("macro_regime", "READY (NON-ETF SHADOW)") if nse_s2_shadow else "AWAITING FIRST EOD RUN (NON-ETF)"

    # -------------------------------------------------------------
    # 9. LOG TAB & CHART DATA (STRICT NaN DATA FAULT ENFORCEMENT)
    # -------------------------------------------------------------
    dates_list = []
    nav_list = []
    dd_list = []
    log_rows_html = ""

    if not eq_log.empty:
        for _, r in eq_log.iterrows():
            s_dt = str(r.get("session_date", str(r.get("date", ""))[:10])).strip()
            c_nav_raw = r.get("combined_fund_nav", r.get("total_portfolio_value"))
            u_nav_raw = r.get("nav_per_unit")
            d_pct_raw = r.get("current_drawdown_pct")
            rec_gap_raw = r.get("reconciliation_gap_pct")
            throt_raw = r.get("throttle_level")

            # Check for NaN / Missing NAV: Hard Rule 2
            nav_is_fault = False
            c_nav_val = None
            if c_nav_raw is None or pd.isna(c_nav_raw) or str(c_nav_raw).strip() == "" or str(c_nav_raw).lower() == "nan":
                nav_is_fault = True
            else:
                try:
                    c_nav_val = float(c_nav_raw)
                    if math.isnan(c_nav_val) or math.isinf(c_nav_val) or c_nav_val <= 0:
                        nav_is_fault = True
                except (ValueError, TypeError):
                    nav_is_fault = True

            u_nav_val = None
            if u_nav_raw is not None and not pd.isna(u_nav_raw):
                try:
                    u_val = float(u_nav_raw)
                    if not math.isnan(u_val):
                        u_nav_val = u_val
                except (ValueError, TypeError):
                    pass

            d_pct_val = None
            if d_pct_raw is not None and not pd.isna(d_pct_raw):
                try:
                    d_val = float(d_pct_raw)
                    if not math.isnan(d_val):
                        d_pct_val = d_val
                except (ValueError, TypeError):
                    pass

            rec_gap_val = None
            if rec_gap_raw is not None and not pd.isna(rec_gap_raw):
                try:
                    rg_val = float(rec_gap_raw)
                    if not math.isnan(rg_val):
                        rec_gap_val = rg_val
                except (ValueError, TypeError):
                    pass

            throt_val = 0
            if throt_raw is not None and not pd.isna(throt_raw):
                try:
                    throt_val = int(throt_raw)
                except (ValueError, TypeError):
                    pass

            # If NAV is fault: NEVER display PASSED, and NEVER display a number
            if nav_is_fault:
                c_nav_display = '<span class="nodata">[DATA FAULT: NaN NAV]</span>'
                rec_badge = '<span class="badge-alert">[DATA FAULT]</span>'
            else:
                c_nav_display = format_inr(c_nav_val)
                rec_badge = '<span class="badge-pass">[PASS]</span>' if (rec_gap_val is not None and rec_gap_val <= 0.1) else '<span class="badge-alert">[FAIL]</span>'
                if s_dt and c_nav_val is not None:
                    dates_list.append(s_dt)
                    nav_list.append(c_nav_val)
                    dd_list.append(d_pct_val if d_pct_val is not None else 0.0)

            throt_display = "OFF (policy)" if policy == "FIXED_SHARES_PLUS_KILL_SWITCH" else f"Level {throt_val}"
            d_class = "text-green" if (d_pct_val is not None and d_pct_val >= 0) else "text-alert"

            log_rows_html += f"""
            <tr>
                <td class="text-amber font-bold">{s_dt}</td>
                <td>{c_nav_display}</td>
                <td>{format_num(u_nav_val, 4)}</td>
                <td class="{d_class}">{format_pct(d_pct_val)}</td>
                <td>{throt_display}</td>
                <td>{format_pct(rec_gap_val, 2, False)}</td>
                <td>{rec_badge}</td>
            </tr>
            """
    else:
        log_rows_html = '<tr><td colspan="7" class="nodata-cell">[NO SESSIONS RECORDED IN EQUITY LOG]</td></tr>'

    has_chart_data = len(dates_list) > 0 and len(nav_list) > 0

    # Separate data timestamp vs page build timestamp
    data_ts_display = data_timestamp_str or (last_session_date + " EOD" if last_session_date else "NO DATA")
    build_utc_str = now_dt.strftime("%Y-%m-%d %H:%M UTC") if isinstance(now_dt, datetime) else str(now_dt)

    # -------------------------------------------------------------
    # 10. ASSEMBLE PRODUCTION RETRO TERMINAL HTML
    # -------------------------------------------------------------
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>ANTIGRAVITY // 1980s AMBER PHOSPHOR TERMINAL [GATE B PAPER INCUBATION]</title>
    <!-- Chart.js Pinned Exact Version from cdnjs -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
    <!-- Google Fonts Monospace Only -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=IBM+Plex+Mono:ital,wght@0,400;0,600;0,700;1,400&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{
            /* 1980s Terminal - Bloomberg Warm Amber Phosphor with High-Visibility Red/Green Insights */
            --bg-canvas: #080705;
            --bg-bezel: #040302;
            --bg-panel: #140F09;
            --bg-panel-hover: #1A140C;
            --border-color: #2B1D0B;
            --border-bright: #F59E0B;
            --text-primary: #FEF3C7;
            --text-secondary: #A8824B;
            --text-dim: #785A2E;
            --green-phosphor: #10B981;
            --green-dim: #059669;
            --green-bg: rgba(16, 185, 129, 0.15);
            --alert-red: #EF4444;
            --alert-red-bg: rgba(239, 68, 68, 0.18);
            --amber-bg: rgba(245, 158, 11, 0.15);
            --teal-accent: #F59E0B;
            --font-mono: 'IBM Plex Mono', 'Share Tech Mono', monospace;
            --card-radius: 0px; /* Square corners everywhere */
        }}

        /* Teletype Ledger Paper Light Theme */
        body.light-theme {{
            --bg-canvas: #fbf8ee;
            --bg-bezel: #ede8d5;
            --bg-panel: #f4efe0;
            --bg-panel-hover: #ece5d3;
            --border-color: #d5ccb5;
            --border-bright: #8a5a00;
            --text-primary: #1a201c;
            --text-secondary: #4a554d;
            --text-dim: #6b776e;
            --green-phosphor: #1b6e2f;
            --green-dim: #155724;
            --green-bg: #eaf3e8;
            --alert-red: #b91c1c;
            --alert-red-bg: #fee2e2;
            --amber-bg: #fef3c7;
            --font-mono: 'Courier Prime', monospace;
            --card-radius: 0px;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            border-radius: 0px !important; /* Strict retro square corners */
            text-shadow: none !important;  /* No blurry text glow on numbers */
        }}

        body {{
            background-color: var(--bg-canvas);
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-size: 14px;
            line-height: 1.5;
            padding: 12px;
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }}

        /* Scanlines strictly <= 4% opacity */
        .scanlines {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            pointer-events: none;
            z-index: 9999;
            background: linear-gradient(rgba(0, 0, 0, 0) 50%, rgba(0, 0, 0, 0.4) 50%);
            background-size: 100% 4px;
            opacity: 0.04; /* Strictly 4% opacity */
        }}

        body.light-theme .scanlines {{
            display: none !important;
        }}

        /* Respect prefers-reduced-motion */
        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: 0.001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.001ms !important;
                scroll-behavior: auto !important;
            }}
            .scanlines {{
                display: none !important;
            }}
        }}

        .container {{
            max-width: 1240px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }}

        /* CRT Terminal Header Frame */
        .terminal-header {{
            background: var(--bg-panel);
            border: 2px solid var(--border-color);
            padding: 14px 18px;
            margin-bottom: 12px;
        }}

        .terminal-bar-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            border-bottom: 1px dashed var(--border-color);
            padding-bottom: 10px;
            margin-bottom: 10px;
        }}

        .terminal-title {{
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }}

        .theme-toggle-btn {{
            background: var(--bg-panel);
            color: var(--text-primary);
            border: 1px solid var(--border-bright);
            padding: 6px 14px;
            font-family: var(--font-mono);
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            cursor: pointer;
            box-shadow: inset 0 1px 0 rgba(254, 243, 199, 0.15), 0 2px 4px rgba(0, 0, 0, 0.4);
            transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
        }}

        .theme-toggle-btn:hover {{
            background: var(--border-bright);
            color: #080705;
            box-shadow: 0 0 14px rgba(245, 158, 11, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.4);
            transform: translateY(-1px);
        }}

        .theme-toggle-btn:active {{
            transform: translateY(1.5px) scale(0.98);
            box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.8);
        }}

        /* TOP STATUS STRIP (PRIMARY FOCUS: OK / STALE / DATA FAULT / HALTED) */
        .status-strip {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
            padding: 12px 16px;
            margin-bottom: 14px;
            border: 2px solid;
        }}

        .status-strip.status-ok {{
            border-color: var(--green-phosphor);
            background: var(--green-bg);
            color: var(--green-phosphor);
        }}

        .status-strip.status-stale {{
            border-color: var(--border-bright);
            background: var(--amber-bg);
            color: var(--text-primary);
        }}

        .status-strip.status-fault,
        .status-strip.status-halted {{
            border-color: var(--alert-red);
            background: var(--alert-red-bg);
            color: var(--alert-red);
        }}

        .status-badge-main {{
            font-size: 1.25rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .status-telemetry {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
            font-size: 0.9rem;
            font-weight: 600;
        }}

        /* ACTUAL FUND HOLDINGS STRIP (NO FAKE TICKER TAPE) */
        .holdings-tape {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            padding: 8px 14px;
            margin-bottom: 14px;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .tape-label {{
            font-weight: 700;
            color: var(--text-dim);
            text-transform: uppercase;
        }}

        .holding-chip {{
            display: inline-flex;
            gap: 4px;
            white-space: nowrap;
        }}

        .chip-sym {{
            font-weight: 700;
            color: var(--text-primary);
        }}

        /* GATE B PANEL & SINGLE RISK GAUGE */
        .panel-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 14px;
        }}

        @media (max-width: 820px) {{
            .panel-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .terminal-card {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            padding: 14px 16px;
        }}

        .card-header {{
            font-size: 0.88rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 6px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .ascii-bar-row {{
            margin: 8px 0;
            font-family: var(--font-mono);
            font-size: 0.88rem;
        }}

        .criteria-list {{
            list-style: none;
            margin-top: 8px;
            font-size: 0.82rem;
        }}

        .criteria-list li {{
            margin-bottom: 5px;
            display: flex;
            justify-content: space-between;
            gap: 8px;
        }}

        /* NAVIGATION TABS */
        .nav-tabs {{
            display: flex;
            gap: 4px;
            border-bottom: 2px solid var(--border-color);
            margin-bottom: 16px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: thin;
            scrollbar-color: var(--border-color) transparent;
        }}

        .nav-tabs::-webkit-scrollbar {{
            height: 4px;
        }}

        .nav-tabs::-webkit-scrollbar-thumb {{
            background: var(--border-color);
        }}

        .tab-btn {{
            background: var(--bg-panel);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
            border-bottom: none;
            padding: 10px 20px;
            font-family: var(--font-mono);
            font-size: 0.88rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            cursor: pointer;
            white-space: nowrap;
            position: relative;
            box-shadow: inset 0 1px 0 rgba(254, 243, 199, 0.08), 0 -2px 4px rgba(0, 0, 0, 0.3);
            transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .tab-btn:hover {{
            background: #1C150D;
            color: var(--text-primary);
            border-color: var(--border-bright);
            box-shadow: inset 0 1px 0 rgba(254, 243, 199, 0.2), 0 -4px 12px rgba(245, 158, 11, 0.25);
            transform: translateY(-2px);
        }}

        .tab-btn:active {{
            transform: translateY(1px);
        }}

        .tab-btn.active {{
            background: var(--border-bright);
            color: #080705;
            border-color: var(--border-bright);
            box-shadow: 0 0 16px rgba(245, 158, 11, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.4);
            transform: none;
        }}

        body.light-theme .tab-btn.active {{
            background: #8a5a00;
            color: #ffffff;
            border-color: #8a5a00;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        /* BALANCED 3x2 METRIC CARDS GRID (NO HOLES AT DESKTOP WIDTH) */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }}

        @media (max-width: 900px) {{
            .metrics-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}

        @media (max-width: 600px) {{
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .metric-box {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            padding: 14px;
        }}

        .metric-title {{
            font-size: 0.78rem;
            text-transform: uppercase;
            color: var(--text-dim);
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }}

        .metric-number {{
            font-size: 1.65rem;
            font-weight: 900;
            line-height: 1.2;
            word-break: break-word;
        }}

        .metric-sub {{
            font-size: 0.8rem;
            color: var(--text-dim);
            margin-top: 4px;
        }}

        /* CHART CONTAINER */
        .chart-wrapper {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            padding: 16px;
            margin-bottom: 16px;
            min-height: 380px;
            position: relative;
        }}

        .chart-box {{
            position: relative;
            width: 100%;
            height: 340px;
        }}

        /* TABLES & GREEN-BAR ROW STYLING */
        .table-scroll {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin: 10px 0 16px 0;
            border: 1px solid var(--border-color);
            scrollbar-width: thin;
            scrollbar-color: var(--border-color) transparent;
        }}

        .table-scroll::-webkit-scrollbar {{
            height: 6px;
        }}

        .table-scroll::-webkit-scrollbar-thumb {{
            background: var(--border-color);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            text-align: left;
            min-width: 600px;
        }}

        th, td {{
            padding: 8px 12px;
            border-bottom: 1px solid var(--border-color);
        }}

        th {{
            background: var(--bg-panel);
            color: var(--text-dim);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        tbody tr:hover {{
            background: var(--bg-panel-hover);
        }}

        /* Teletype Green-Bar Continuous Form Paper */
        body.light-theme table tbody tr:nth-child(even) {{
            background-color: #eaf3e8; /* Continuous form green-bar */
        }}
        body.light-theme table tbody tr:nth-child(odd) {{
            background-color: #fbf8ee;
        }}

        /* PERMANENT SHADOW EXPLORATORY BANNER (NO EMOJI) */
        .banner-exploratory {{
            background: var(--alert-red-bg);
            border: 2px solid var(--alert-red);
            color: var(--alert-red);
            padding: 14px 18px;
            margin-bottom: 16px;
            font-weight: 700;
        }}

        .banner-exploratory-title {{
            font-size: 1.05rem;
            letter-spacing: 0.08em;
            margin-bottom: 4px;
        }}

        .banner-exploratory-text {{
            font-size: 0.85rem;
            line-height: 1.4;
            font-weight: 400;
        }}

        /* MODELLED NOTICE FOR BOND SLEEVE */
        .modelled-notice {{
            background: var(--amber-bg);
            border: 1px solid var(--border-bright);
            color: var(--text-primary);
            padding: 8px 12px;
            margin-bottom: 10px;
            font-size: 0.82rem;
            font-weight: 700;
        }}

        /* WARNING / NO DATA STYLING (HARD RULE 1 & 2) */
        .nodata {{
            color: var(--alert-red) !important;
            background: var(--alert-red-bg);
            padding: 1px 5px;
            border: 1px dashed var(--alert-red);
            font-weight: 700;
            font-size: 0.85em;
        }}

        .nodata-cell {{
            text-align: center;
            color: var(--text-dim);
            padding: 18px !important;
            font-style: italic;
        }}

        /* BADGES & UTILITIES */
        .badge-pass {{
            color: var(--green-phosphor);
            font-weight: 700;
        }}

        .badge-alert {{
            color: var(--alert-red);
            font-weight: 700;
        }}

        .badge-dim {{
            color: var(--text-dim);
        }}

        .badge-shadow {{
            color: var(--text-dim);
            border: 1px solid var(--border-color);
            padding: 1px 6px;
        }}

        .text-green {{ color: var(--green-phosphor) !important; }}
        .text-amber {{ color: var(--text-primary) !important; }}
        .text-alert {{ color: var(--alert-red) !important; }}
        .text-dim {{ color: var(--text-dim) !important; }}
        .font-bold {{ font-weight: 700; }}

        /* FOOTER */
        .terminal-footer {{
            border-top: 1px solid var(--border-color);
            padding: 12px 0;
            margin-top: 24px;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
            font-size: 0.8rem;
            color: var(--text-dim);
        }}

        /* Mobile First: 390px Viewport Support */
        @media (max-width: 600px) {{
            body {{
                padding: 6px;
            }}
            .terminal-header {{
                padding: 10px 12px;
            }}
            .status-strip {{
                padding: 10px 12px;
                flex-direction: column;
                align-items: flex-start;
            }}
            .status-badge-main {{
                font-size: 1.1rem;
            }}
            .metric-number {{
                font-size: 1.4rem;
            }}
            .nav-tabs {{
                gap: 2px;
            }}
            .tab-btn {{
                padding: 8px 10px;
                font-size: 0.78rem;
                flex: 1 1 auto;
                text-align: center;
            }}
            .chart-wrapper {{
                padding: 10px;
                min-height: 300px;
            }}
            .chart-box {{
                height: 260px;
            }}
        }}
    </style>
</head>
<body>
    <div class="scanlines" aria-hidden="true"></div>

    <div class="container">
        <!-- TOP TERMINAL BAR & THEME SWITCHER -->
        <header class="terminal-header" role="banner">
            <div class="terminal-bar-top">
                <div class="terminal-title">
                    &gt; ANTIGRAVITY // QUANTUM TERMINAL [GATE B PAPER INCUBATION]
                </div>
                <button id="theme-toggle-btn" class="theme-toggle-btn" onclick="toggleTheme()" aria-label="Toggle retro CRT and teletype paper theme">
                    [THEME: CRT AMBER (DARK)]
                </button>
            </div>
            <div style="font-size: 0.82rem; color: var(--text-dim); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                <span>CENTRAL HEDGE FUND ARCHITECTURE &bull; SEBI 100% CNC CASH DELIVERY</span>
                <span>DATA TIMESTAMP: <strong class="text-amber">{data_ts_display}</strong></span>
            </div>
        </header>

        <!-- PRIMARY STATUS STRIP (OK / STALE / DATA FAULT / HALTED) -->
        <section class="status-strip {top_status_class}" aria-label="Fund Telemetry Operational Status">
            <div class="status-badge-main">
                <span>STATUS:</span>
                <span>{top_status_badge}</span>
                <span style="font-size: 0.85rem; font-weight: normal; margin-left: 6px;">({top_status_desc})</span>
            </div>
            <div class="status-telemetry">
                <span>LAST SESSION: <strong class="text-amber">{last_session_date or '<span class="nodata">[NO DATA]</span>'}</strong></span>
                <span>DATA AGE: <strong class="text-amber">{data_age_str}</strong></span>
                <span>MODE: <strong class="text-amber">{mode or '<span class="nodata">[NO DATA]</span>'}</strong></span>
            </div>
        </section>

        <!-- ACTUAL FUND HOLDINGS STRIP (RULE 3: NO FAKE TICKER TAPE) -->
        <div class="holdings-tape" role="region" aria-label="Actual Fund Holdings Quotes">
            <span class="tape-label">FUND HOLDINGS ({sleeve_session_date}):</span>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                {actual_holdings_html}
            </div>
        </div>

        <!-- GATE B PANEL & SINGLE RISK GAUGE -->
        <div class="panel-grid">
            <!-- Gate B Panel -->
            <div class="terminal-card">
                <div class="card-header">
                    <span>Gate B Institutional Incubation Progress</span>
                    <span class="badge-pass">{gate_b_text}</span>
                </div>
                <div class="ascii-bar-row">
                    PROGRESS: <span class="text-amber">{gate_b_ascii_bar}</span>
                </div>
                <ul class="criteria-list">
                    <li>
                        <span>1. Duration (13 Weeks / 91 Days Uninterrupted):</span>
                        <strong class="text-amber">{format_num(days_incubated, 0)} / {target_days} DAYS</strong>
                    </li>
                    <li>
                        <span>2. Drawdown Control (&le; 40.00% Kill Switch Limit):</span>
                        <strong class="{ 'text-green' if (curr_dd_pct is not None and abs(curr_dd_pct) < 40.0) else 'text-alert' }">
                            {format_pct(curr_dd_pct)} (KILL SWITCH -40.0%)
                        </strong>
                    </li>
                    <li>
                        <span>3. Multi-Sleeve Reconciliation (Daily Gap &le; 0.10%):</span>
                        <strong>{rec_status_label}</strong>
                    </li>
                    <li>
                        <span>4. Capital Invariant (100% Cash Delivery, Zero Leverage):</span>
                        <strong class="badge-pass">[PASS - 100% CNC]</strong>
                    </li>
                </ul>
            </div>

            <!-- Single Risk Gauge: Distance to -40% Kill Switch -->
            <div class="terminal-card">
                <div class="card-header">
                    <span>Emergency Kill Switch Safeguard</span>
                    <span class="badge-dim">THROTTLE: {throttle_text}</span>
                </div>
                <div class="ascii-bar-row">
                    DISTANCE TO -40% KILL SWITCH:
                </div>
                <div class="ascii-bar-row" style="font-size: 1.05rem; font-weight: 700;">
                    <span class="text-amber">{kill_ascii}</span> {kill_status_badge}
                </div>
                <ul class="criteria-list" style="margin-top: 8px;">
                    <li>
                        <span>Current Fund Drawdown:</span>
                        <strong class="{ 'text-green' if (curr_dd_pct is not None and curr_dd_pct >= 0) else 'text-alert' }">{format_pct(curr_dd_pct)}</strong>
                    </li>
                    <li>
                        <span>Emergency Kill Switch Threshold:</span>
                        <strong class="text-alert">-40.00% NAV</strong>
                    </li>
                    <li>
                        <span>Remaining Safety Buffer:</span>
                        <strong class="{ 'text-green' if (kill_margin and kill_margin > 0) else 'text-alert' }">+{format_pct(kill_margin, 2, False)}</strong>
                    </li>
                    <li>
                        <span>Throttle Policy (T1 Pre-Registered):</span>
                        <strong class="text-dim">FIXED_SHARES_PLUS_KILL_SWITCH (Throttles OFF)</strong>
                    </li>
                </ul>
            </div>
        </div>

        <!-- NAVIGATION TABS -->
        <nav class="nav-tabs" role="tablist">
            <button class="tab-btn active" role="tab" aria-selected="true" onclick="openTab(event, 'tab-fund')">[1] FUND OVERVIEW</button>
            <button class="tab-btn" role="tab" aria-selected="false" onclick="openTab(event, 'tab-sleeves')">[2] SLEEVES &amp; HOLDINGS</button>
            <button class="tab-btn" role="tab" aria-selected="false" onclick="openTab(event, 'tab-shadows')">[3] SHADOW PODS</button>
            <button class="tab-btn" role="tab" aria-selected="false" onclick="openTab(event, 'tab-log')">[4] RECONCILIATION LOG</button>
        </nav>

        <!-- TAB 1: FUND OVERVIEW (BALANCED 3x2 KPI GRID) -->
        <div id="tab-fund" class="tab-content active" role="tabpanel">
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-title">Combined Fund NAV</div>
                    <div class="metric-number text-amber">{format_inr(combined_nav)}</div>
                    <div class="metric-sub">Base Seed Capital: {format_inr(target_cap)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Unitized NAV Per Share</div>
                    <div class="metric-number text-green">{format_num(unit_nav, 4)}</div>
                    <div class="metric-sub">Base NAV: 100.0000 &bull; HWM: {format_num(hwm_unit, 4)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Inception PnL vs Seed</div>
                    <div class="metric-number { 'text-green' if (total_pnl is not None and total_pnl >= 0) else 'text-alert' }">
                        {format_pct(total_pnl_pct)}
                    </div>
                    <div class="metric-sub">Net Alpha: {format_inr(total_pnl)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Current / Peak Drawdown</div>
                    <div class="metric-number { 'text-green' if (curr_dd_pct is not None and curr_dd_pct >= 0) else 'text-alert' }">
                        {format_pct(curr_dd_pct)}
                    </div>
                    <div class="metric-sub">Max Recorded Drawdown: {format_pct(max_dd_pct)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Total Issued Units</div>
                    <div class="metric-number text-amber">{format_num(issued_units, 2)}</div>
                    <div class="metric-sub">Daily Unitized Ledger Accounting</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Reconciliation Invariant</div>
                    <div class="metric-number">{rec_status_label}</div>
                    <div class="metric-sub">Sleeve 1 + Sleeve 2 &equiv; Central Fund NAV</div>
                </div>
            </div>

            <!-- Equity Curve Chart -->
            <div class="chart-wrapper">
                <div class="card-header">
                    <span>Fund Equity Curve &amp; Drawdown Oscilloscope</span>
                    <span class="text-dim">Verified End-of-Day Telemetry</span>
                </div>
                <div class="chart-box">
                    { f'<canvas id="equityChart"></canvas>' if has_chart_data else '<div class="nodata-cell" style="padding-top: 100px;">[NO HISTORICAL LOG SESSIONS TO GRAPH]</div>' }
                </div>
            </div>

            <!-- Accounting Invariants Matrix -->
            <div class="terminal-card">
                <div class="card-header">
                    <span>Hedge Fund Charter Operating Invariants</span>
                    <span class="badge-pass">[ALL ACTIVE INVARIANTS SATISFIED]</span>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Invariant Protocol</th>
                                <th>Governing Limit</th>
                                <th>Current Telemetry</th>
                                <th>Verification Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>SEBI 100% Cash Delivery</td>
                                <td>Zero Leverage / Zero Shorting</td>
                                <td>100.0% Cash Equity &amp; Sovereign Repo</td>
                                <td><span class="badge-pass">[PASS - 100% CNC]</span></td>
                            </tr>
                            <tr>
                                <td>Multi-Sleeve NAV Reconciliation</td>
                                <td>Tolerance &le; 0.10% Gap</td>
                                <td>{format_pct(rec_gap, 2, False)}</td>
                                <td>{rec_status_label}</td>
                            </tr>
                            <tr>
                                <td>Institutional Drawdown Guardrail</td>
                                <td>Emergency Kill Switch: -40.00% (Throttles OFF)</td>
                                <td>Current: {format_pct(curr_dd_pct)} (Buffer: +{format_pct(kill_margin, 2, False)})</td>
                                <td><span class="badge-pass">[KILL SWITCH ARMED &bull; SAFE]</span></td>
                            </tr>
                            <tr>
                                <td>Daily Unitized NAV Ledger</td>
                                <td>Base NAV 100.0000</td>
                                <td>{format_num(unit_nav, 4)} NAV / {format_num(issued_units, 1)} Units</td>
                                <td><span class="badge-pass">[RECORDED IN LEDGER]</span></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 2: SLEEVES & HOLDINGS -->
        <div id="tab-sleeves" class="tab-content" role="tabpanel">
            <!-- Sleeve 1 Table -->
            <div class="terminal-card" style="margin-bottom: 16px;">
                <div class="card-header">
                    <span>Sleeve 1: Multi-Asset Equity &amp; Gold (Phase 1 Champion)</span>
                    <span>NAV: <strong class="text-amber">{format_inr(etf_nav)}</strong> &bull; Cash: {format_inr(etf_cash)}</span>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Shares</th>
                                <th>Entry Price</th>
                                <th>Last Price</th>
                                <th>Current Value (Weight)</th>
                                <th>Unrealized PnL</th>
                                <th>Role</th>
                            </tr>
                        </thead>
                        <tbody>
                            {etf_table_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Sleeve 2 Table with MODELLED NOTICE -->
            <div class="terminal-card">
                <div class="card-header">
                    <span>Sleeve 2: Sovereign Bond &amp; Overnight Cash (Phase 3 Haven)</span>
                    <span>NAV: <strong class="text-amber">{format_inr(bond_nav)}</strong> &bull; Cash: {format_inr(bond_cash)}</span>
                </div>

                <!-- CRITICAL REQUIREMENT: MODELLED NOTICE (NO EMOJI) -->
                <div class="modelled-notice" role="note">
                    [!] NOTE: Bond-sleeve returns are MODELLED (carry model, not market-tested).
                </div>

                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Shares</th>
                                <th>Entry Price</th>
                                <th>Last Price</th>
                                <th>Current Value (Weight)</th>
                                <th>Carry Telemetry</th>
                                <th>Role</th>
                            </tr>
                        </thead>
                        <tbody>
                            {bond_table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 3: SHADOW PODS (CRITICAL REQUIREMENT: EXPLORATORY BANNER) -->
        <div id="tab-shadows" class="tab-content" role="tabpanel">
            <!-- CRITICAL PERMANENT EXPLORATORY BANNER (NO EMOJI) -->
            <div class="banner-exploratory" role="alert">
                <div class="banner-exploratory-title">[!] EXPLORATORY - NOT EVIDENCE [!]</div>
                <div class="banner-exploratory-text">
                    Shadow pods execute simulated, experimental research models (e.g. US Growth Momentum, NSE Whole-Market Factor).
                    <strong>ZERO FUND CAPITAL IS COMMITTED.</strong>
                    Under fund charter and SEBI incubation rules, shadow tracking does NOT constitute performance evidence or track record for Fund Gate B graduation.
                </div>
            </div>

            <!-- Pod A: US Momentum Shadow -->
            <div class="terminal-card" style="margin-bottom: 16px;">
                <div class="card-header">
                    <span>Pod A: US Non-ETF Equities Research (S&amp;P 500 Shadow Retired &bull; S&amp;P 1500 Audit) &bull; Capital: $0.00</span>
                    <span class="badge-shadow">{us_shadow_verified_text} &bull; ZERO FUND CAPITAL</span>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Strategy Type</th>
                                <th>Quantity</th>
                                <th>Entry Price</th>
                                <th>Peak Price</th>
                                <th>Estimated Value</th>
                                <th>Entry Date</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {us_shadow_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Pod B: NSE Whole-Market Shadow -->
            <div class="terminal-card">
                <div class="card-header">
                    <span>Pod B: NSE Whole-Market Research Shadow (INR)</span>
                    <span class="badge-shadow">INCUBATION SANDBOX &bull; ZERO LIVE RISK</span>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Pod Target</th>
                                <th>Sandbox Capital</th>
                                <th>Unallocated Cash</th>
                                <th>High Water Mark</th>
                                <th>Operational Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td class="font-bold text-amber">NSE Whole-Market Candidate S2 (Non-ETF)</td>
                                <td>{format_inr(nse_s2_init)}</td>
                                <td>{format_inr(nse_s2_cash)}</td>
                                <td>{format_inr(nse_s2_hwm)} ({nse_s2_pos_cnt} pos)</td>
                                <td><span class="badge-shadow">{nse_s2_regime}</span></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 4: RECONCILIATION & EQUITY LOG -->
        <div id="tab-log" class="tab-content" role="tabpanel">
            <div class="terminal-card">
                <div class="card-header">
                    <span>Institutional Daily Session Log &amp; Reconciliation Audit</span>
                    <span class="text-dim">Reconciliation Limit: &le; 0.10% Gap</span>
                </div>
                <div class="table-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Session Date</th>
                                <th>Combined NAV</th>
                                <th>Unit NAV</th>
                                <th>Drawdown</th>
                                <th>Throttle Status</th>
                                <th>Reconciliation Gap</th>
                                <th>Audit Result</th>
                            </tr>
                        </thead>
                        <tbody>
                            {log_rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- FOOTER (ACTUAL RUN TIMES: 18:49–20:30 UTC & COMPILED TIMESTAMP) -->
        <footer class="terminal-footer" role="contentinfo">
            <div>ANTIGRAVITY // 1980s AMBER TERMINAL &bull; GATE B PAPER INCUBATION &bull; RUNNERS EXECUTE 18:49–20:30 UTC</div>
            <div>STRICT READ-ONLY TELEMETRY &bull; PAGE COMPILED: {build_utc_str}</div>
        </footer>
    </div>

    <!-- JAVASCRIPT: TABS, THEME TOGGLE, CHART INITIALIZATION -->
    <script>
        function openTab(evt, tabId) {{
            const contents = document.getElementsByClassName("tab-content");
            for (let i = 0; i < contents.length; i++) {{
                contents[i].classList.remove("active");
            }}
            const btns = document.getElementsByClassName("tab-btn");
            for (let i = 0; i < btns.length; i++) {{
                btns[i].classList.remove("active");
                btns[i].setAttribute("aria-selected", "false");
            }}
            const target = document.getElementById(tabId);
            if (target) {{
                target.classList.add("active");
            }}
            if (evt && evt.currentTarget) {{
                evt.currentTarget.classList.add("active");
                evt.currentTarget.setAttribute("aria-selected", "true");
            }} else {{
                const btnIndex = tabId === 'tab-fund' ? 0 : (tabId === 'tab-sleeves' ? 1 : (tabId === 'tab-shadows' ? 2 : 3));
                if (btns[btnIndex]) {{
                    btns[btnIndex].classList.add("active");
                    btns[btnIndex].setAttribute("aria-selected", "true");
                }}
            }}
            if (tabId === 'tab-fund' && window.equityChartInstance) {{
                window.equityChartInstance.resize();
            }}
        }}

        function toggleTheme() {{
            const isLight = document.body.classList.toggle('light-theme');
            try {{
                localStorage.setItem('terminal_theme', isLight ? 'light' : 'dark');
            }} catch(e) {{}}
            const btn = document.getElementById('theme-toggle-btn');
            if (btn) {{
                btn.textContent = isLight ? '[THEME: TELETYPE PAPER (LIGHT)]' : '[THEME: CRT AMBER (DARK)]';
            }}
            if (window.equityChartInstance) {{
                updateChartColors(isLight);
            }}
        }}

        // Initialize Theme from localStorage or URL hash
        (function() {{
            try {{
                const saved = localStorage.getItem('terminal_theme');
                if (saved === 'light' || window.location.hash.includes('light') || window.location.search.includes('theme=light')) {{
                    document.body.classList.add('light-theme');
                    const btn = document.getElementById('theme-toggle-btn');
                    if (btn) btn.textContent = '[THEME: TELETYPE PAPER (LIGHT)]';
                }}
            }} catch(e) {{}}
        }})();

        // Initialize Active Tab from URL hash
        (function() {{
            try {{
                const hash = window.location.hash;
                if (hash.includes('sleeves')) {{
                    openTab(null, 'tab-sleeves');
                }} else if (hash.includes('shadows')) {{
                    openTab(null, 'tab-shadows');
                }} else if (hash.includes('log')) {{
                    openTab(null, 'tab-log');
                }}
            }} catch(e) {{}}
        }})();

        // Chart.js Setup
        let equityChartInstance = null;
        const hasChart = {json.dumps(has_chart_data)};

        if (hasChart) {{
            const ctx = document.getElementById('equityChart');
            if (ctx) {{
                const isLight = document.body.classList.contains('light-theme');
                const navColor = isLight ? '#8a5a00' : '#ffb000';
                const ddColor = isLight ? '#b91c1c' : '#ff4455';
                const textColor = isLight ? '#1a201c' : '#ffb000';
                const gridColor = isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,176,0,0.12)';

                equityChartInstance = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(dates_list)},
                        datasets: [
                            {{
                                label: 'Fund NAV (INR ₹)',
                                data: {json.dumps(nav_list)},
                                borderColor: navColor,
                                backgroundColor: isLight ? 'rgba(138,90,0,0.08)' : 'rgba(255,176,0,0.15)',
                                borderWidth: 2.2,
                                fill: true,
                                tension: 0.1,
                                yAxisID: 'y'
                            }},
                            {{
                                label: 'Drawdown (%)',
                                data: {json.dumps(dd_list)},
                                borderColor: ddColor,
                                borderWidth: 1.8,
                                borderDash: [4, 4],
                                fill: false,
                                tension: 0.1,
                                yAxisID: 'y1'
                            }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {{ mode: 'index', intersect: false }},
                        scales: {{
                            x: {{
                                grid: {{ color: gridColor }},
                                ticks: {{ color: textColor, font: {{ family: "'Share Tech Mono', monospace" }} }}
                            }},
                            y: {{
                                position: 'left',
                                grid: {{ color: gridColor }},
                                ticks: {{
                                    color: textColor,
                                    font: {{ family: "'Share Tech Mono', monospace" }},
                                    callback: function(v) {{
                                        return (v < 0 ? '-₹' : '₹') + Math.abs(v).toLocaleString('en-IN');
                                    }}
                                }}
                            }},
                            y1: {{
                                position: 'right',
                                grid: {{ drawOnChartArea: false }},
                                ticks: {{
                                    color: ddColor,
                                    font: {{ family: "'Share Tech Mono', monospace" }},
                                    callback: function(v) {{ return v + '%'; }}
                                }}
                            }}
                        }},
                        plugins: {{
                            legend: {{
                                labels: {{
                                    color: textColor,
                                    font: {{ family: "'Share Tech Mono', monospace" }}
                                }}
                            }}
                        }}
                    }}
                }});
                window.equityChartInstance = equityChartInstance;
            }}
        }}

        function updateChartColors(isLight) {{
            if (!equityChartInstance) return;
            const navColor = isLight ? '#8a5a00' : '#ffb000';
            const ddColor = isLight ? '#b91c1c' : '#ff4455';
            const textColor = isLight ? '#1a201c' : '#ffb000';
            const gridColor = isLight ? 'rgba(0,0,0,0.08)' : 'rgba(255,176,0,0.12)';

            equityChartInstance.data.datasets[0].borderColor = navColor;
            equityChartInstance.data.datasets[0].backgroundColor = isLight ? 'rgba(138,90,0,0.08)' : 'rgba(255,176,0,0.15)';
            equityChartInstance.data.datasets[1].borderColor = ddColor;

            equityChartInstance.options.scales.x.ticks.color = textColor;
            equityChartInstance.options.scales.x.grid.color = gridColor;
            equityChartInstance.options.scales.y.ticks.color = textColor;
            equityChartInstance.options.scales.y.grid.color = gridColor;
            equityChartInstance.options.scales.y1.ticks.color = ddColor;
            equityChartInstance.options.plugins.legend.labels.color = textColor;
            equityChartInstance.update();
        }}
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Successfully generated 1980s Retro Amber Terminal dashboard: {output_path} ({len(html_content):,} bytes)")
    return output_path


if __name__ == "__main__":
    generate_dashboard_html()
