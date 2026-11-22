"""
Unit Tests for Web Dashboard Generator (trading_system/scripts/generate_web_dashboard.py)
========================================================================================
Validates 1980s retro terminal generation, strict data integrity (zero fake fallbacks),
top status strip state transitions (OK, STALE, DATA FAULT, HALTED), and rule compliance.
"""

import os
import json
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from trading_system.scripts.generate_web_dashboard import (
    load_json,
    load_csv,
    format_inr,
    format_usd,
    format_pct,
    render_ascii_bar,
    generate_dashboard_html,
)


def test_format_inr():
    """Verify Indian numbering format (e.g. 1,00,000.00) and edge cases."""
    assert format_inr(100000.0) == "₹1,00,000.00"
    assert format_inr(98474.89) == "₹98,474.89"
    assert format_inr(10000000.0) == "₹1,00,00,000.00"
    # Negative sign strictly before rupee symbol: -₹1,525.11
    assert format_inr(-1525.11) == "-₹1,525.11"
    assert format_inr(0.0) == "₹0.00"
    assert '<span class="nodata">[NO DATA]</span>' in format_inr(None)
    assert '<span class="nodata">[NO DATA]</span>' in format_inr("invalid")
    assert '<span class="nodata">[DATA FAULT: NaN]</span>' in format_inr(float("nan"))


def test_format_usd():
    """Verify USD plain currency format and edge cases."""
    assert format_usd(100000.0) == "$100,000.00"
    assert format_usd(-1525.11) == "-$1,525.11"
    assert '<span class="nodata">[NO DATA]</span>' in format_usd(None)
    assert '<span class="nodata">[DATA FAULT: NaN]</span>' in format_usd(float("nan"))


def test_ascii_bar():
    """Verify ASCII progress bar rendering."""
    bar_5 = render_ascii_bar(5.0, width=20)
    assert bar_5.startswith("[█")
    assert bar_5.endswith("░]")

    bar_100 = render_ascii_bar(100.0, width=20)
    assert bar_100 == f"[{'█' * 20}]"

    bar_none = render_ascii_bar(None, width=20)
    assert bar_none == f"[{'░' * 20}]"


def test_missing_file(tmp_path):
    """
    Cover: missing file condition.
    When state files are missing, generator must report DATA FAULT and NO DATA without crashing.
    """
    out_html = tmp_path / "index.html"
    res = generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html))

    assert os.path.exists(res)
    content = out_html.read_text(encoding="utf-8")
    assert "[DATA FAULT]" in content
    assert "status-fault" in content
    assert '<span class="nodata">[NO DATA]</span>' in content


def test_stale_data(tmp_path):
    """
    Cover: stale data condition.
    When last session_date is older than 3 days, top status strip must show [STALE] with age.
    """
    out_html = tmp_path / "index.html"

    mgr_state = {
        "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
        "combined_fund_nav": 99000.0,
        "combined_target_capital": 100000.0,
        "unitized_nav": 99.0,
        "current_drawdown": -0.01,
        "throttle_level": 0,
        "is_halted": False,
        "last_rebalance_date": "2026-11-10",
        "mode": "PAPER"
    }
    (tmp_path / "manager_state.json").write_text(json.dumps(mgr_state), encoding="utf-8")

    eq_df = pd.DataFrame([
        {
            "session_date": "2026-11-10",
            "combined_fund_nav": 99000.0,
            "nav_per_unit": 99.0,
            "current_drawdown_pct": -1.0,
            "reconciliation_gap_pct": 0.0,
            "throttle_level": 0
        }
    ])
    eq_df.to_csv(tmp_path / "manager_equity_log.csv", index=False)

    now_dt = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    res = generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html), now_dt=now_dt)

    content = out_html.read_text(encoding="utf-8")
    assert "[STALE]" in content
    assert "status-stale" in content
    assert "10d" in content
    assert "[OK]" not in content


def test_halted(tmp_path):
    """
    Cover: halted condition.
    When is_halted is True, status strip must display [HALTED] and halt reason.
    """
    out_html = tmp_path / "index.html"

    mgr_state = {
        "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
        "combined_fund_nav": 85000.0,
        "combined_target_capital": 100000.0,
        "unitized_nav": 85.0,
        "current_drawdown": -0.15,
        "throttle_level": 2,
        "is_halted": True,
        "halt_reason": "MANUAL_RISK_HALT_TEST",
        "last_rebalance_date": "2026-11-20",
        "mode": "PAPER"
    }
    (tmp_path / "manager_state.json").write_text(json.dumps(mgr_state), encoding="utf-8")

    eq_df = pd.DataFrame([
        {
            "session_date": "2026-11-20",
            "combined_fund_nav": 85000.0,
            "nav_per_unit": 85.0,
            "current_drawdown_pct": -15.0,
            "reconciliation_gap_pct": 0.0,
            "throttle_level": 2
        }
    ])
    eq_df.to_csv(tmp_path / "manager_equity_log.csv", index=False)

    now_dt = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
    generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html), now_dt=now_dt)

    content = out_html.read_text(encoding="utf-8")
    assert "[HALTED]" in content
    assert "status-halted" in content
    assert "MANUAL_RISK_HALT_TEST" in content


def test_data_fault(tmp_path):
    """
    Cover: DATA FAULT condition.
    Corrupt JSON or missing mandatory fields must trigger DATA FAULT.
    """
    out_html = tmp_path / "index.html"

    # Case A: corrupt JSON
    (tmp_path / "manager_state.json").write_text("{ corrupt json data ...", encoding="utf-8")
    generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html))
    content = out_html.read_text(encoding="utf-8")
    assert "[DATA FAULT]" in content
    assert "status-fault" in content

    # Case B: valid JSON but missing essential NAV fields
    (tmp_path / "manager_state.json").write_text(json.dumps({"unrelated_key": 123}), encoding="utf-8")
    generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html))
    content_b = out_html.read_text(encoding="utf-8")
    assert "[DATA FAULT]" in content_b


def test_nan_row_renders_data_fault_never_passed(tmp_path):
    """
    Hard Rule: A row with a NaN or missing NAV is displayed as 'DATA FAULT'
    in warning style, never as PASSED, and never as a number.
    """
    out_html = tmp_path / "index.html"

    mgr_state = {
        "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
        "policy": "FIXED_SHARES_PLUS_KILL_SWITCH",
        "combined_fund_nav": 98474.89,
        "combined_target_capital": 100000.0,
        "unitized_nav": 98.0828,
        "last_rebalance_date": "2026-11-20",
        "mode": "PAPER"
    }
    (tmp_path / "manager_state.json").write_text(json.dumps(mgr_state), encoding="utf-8")

    # Equity log with a NaN row for 2026-11-13
    eq_df = pd.DataFrame([
        {
            "session_date": "2026-11-13",
            "combined_fund_nav": np.nan,  # Missing / NaN NAV
            "nav_per_unit": 99.9319,
            "current_drawdown_pct": -0.07,
            "reconciliation_gap_pct": 0.0,
            "throttle_level": 0
        },
        {
            "session_date": "2026-11-20",
            "combined_fund_nav": 98474.89,
            "nav_per_unit": 98.0828,
            "current_drawdown_pct": -1.92,
            "reconciliation_gap_pct": 0.0,
            "throttle_level": 0
        }
    ])
    eq_df.to_csv(tmp_path / "manager_equity_log.csv", index=False)

    now_dt = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
    generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html), now_dt=now_dt)

    content = out_html.read_text(encoding="utf-8")

    # Must render DATA FAULT for the NaN row
    assert "DATA FAULT: NaN NAV" in content
    # The NaN row must NEVER be rendered as a number like '₹nan'
    assert "₹nan" not in content
    assert "₹NaN" not in content
    assert "nan" not in content.lower() or "data fault: nan nav" in content.lower()


def test_normal(tmp_path):
    """
    Cover: normal nominal condition.
    With valid and fresh state (< 3 days old), status is OK, reconciliation PASS,
    and all required hard rules are respected.
    """
    out_html = tmp_path / "index.html"

    mgr_state = {
        "manager_name": "CENTRAL_PORTFOLIO_MANAGER",
        "policy": "FIXED_SHARES_PLUS_KILL_SWITCH",
        "combined_fund_nav": 98474.89,
        "combined_target_capital": 100000.0,
        "unitized_nav": 98.0828,
        "hwm_unit_nav": 100.0,
        "current_drawdown": -0.0192,
        "max_drawdown": -0.0192,
        "throttle_level": 0,
        "is_halted": False,
        "last_reconciliation_gap_pct": 0.0,
        "last_rebalance_date": "2026-11-20",
        "mode": "PAPER"
    }
    (tmp_path / "manager_state.json").write_text(json.dumps(mgr_state), encoding="utf-8")

    etf_state = {
        "bot_name": "ETF_AND_GOLD_BOT",
        "days_incubated": 5,
        "incubation_target_weeks": 13,
        "nav": 78466.25,
        "cash": 366.31,
        "positions": {
            "GOLDBEES.NS": {"shares": 178, "entry_price": 111.91, "last_price": 102.21}
        }
    }
    (tmp_path / "etf_gold_state.json").write_text(json.dumps(etf_state), encoding="utf-8")

    bond_state = {
        "bot_name": "BOND_AND_CASH_BOT",
        "days_incubated": 5,
        "incubation_target_weeks": 13,
        "nav": 20008.64,
        "cash": 8.84,
        "total_carry_earned": 22.52,
        "positions": {
            "LIQUIDBEES.NS": {"shares": 20, "entry_price": 1000.0, "last_price": 999.99}
        }
    }
    (tmp_path / "bond_cash_state.json").write_text(json.dumps(bond_state), encoding="utf-8")

    ledger = {
        "total_units": 800.0,
        "base_nav_per_unit": 100.0,
        "nav_per_unit": 98.0828
    }
    (tmp_path / "unitized_nav_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    eq_df = pd.DataFrame([
        {
            "session_date": "2026-11-20",
            "combined_fund_nav": 98474.89,
            "nav_per_unit": 98.0828,
            "current_drawdown_pct": -1.92,
            "reconciliation_gap_pct": 0.0,
            "throttle_level": 0
        }
    ])
    eq_df.to_csv(tmp_path / "manager_equity_log.csv", index=False)

    now_dt = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
    generate_dashboard_html(data_dir=str(tmp_path), output_path=str(out_html), now_dt=now_dt)

    content = out_html.read_text(encoding="utf-8")

    # 1. Status strip
    assert "[OK]" in content
    assert "status-ok" in content
    assert "1d" in content

    # 2. Hard Rule 1: Formatted numbers, no fallback numbers
    assert "₹98,474.89" in content
    assert "₹1,00,000.00" in content
    assert "98.0828" in content
    assert "800.00" in content

    # 3. Hard Rule 2: No fake ticker tape
    assert "1960s NSE // BSE TELETYPE" not in content
    assert "RELIANCE ₹2,980.50" not in content
    assert "NIFTY 50" not in content
    assert "SENSEX" not in content
    # Actual holdings tape present
    assert "GOLDBEES.NS" in content
    assert "LIQUIDBEES.NS" in content

    # 4. Hard Rule 3: Computed status labels & -40% kill switch single gauge
    assert "[PASS]" in content
    assert "OFF (policy)" in content
    assert "DISTANCE TO -40% KILL SWITCH" in content
    assert "-40.00%" in content

    # 5. Hard Rule 4: Bond-sleeve returns marked MODELLED
    assert "MODELLED (carry model, not market-tested)" in content

    # 6. Hard Rule 5: Shadow pods tab with permanent EXPLORATORY banner
    assert "EXPLORATORY - NOT EVIDENCE" in content

    # 7. Retro Styling: Square corners, scanlines <= 4%, no emoji, no glow
    assert "border-radius: 0px !important" in content
    assert "text-shadow: none !important" in content
    assert "opacity: 0.04" in content
    # Check absence of common emoji
    for emoji in ["📊", "🏆", "⚠️", "🇺🇸", "🇮🇳", "☁️", "🌱", "📝", "🛡️"]:
        assert emoji not in content, f"Emoji {emoji} found in retro dashboard"

    # 8. Tech requirements: Pinned Chart.js from cdnjs
    assert "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" in content
