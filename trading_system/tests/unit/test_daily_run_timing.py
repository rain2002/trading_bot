import os
import pytest
from trading_system.app.config.market_config import MarketConfig


def test_market_config_timing_and_execution_rules():
    """
    Asserts Indian and US market configurations reflect official execution schedule:
    - India: 14:45 pre-scan, 15:15 rebalance dispatch, 15:25 cutoff, 0.2% limit buffer.
    - US: 15:15 pre-scan, 15:45 rebalance dispatch, 15:55 cutoff, 0.2% limit buffer.
    """
    # India
    cfg_in = MarketConfig.load("IN")
    assert cfg_in.trading_timezone == "Asia/Kolkata"
    assert cfg_in.open_time == "09:15"
    assert cfg_in.close_time == "15:30"
    assert cfg_in.pre_market_scan == "14:45"
    assert cfg_in.rebalance_dispatch == "15:15"
    assert cfg_in.order_cutoff == "15:25"
    assert cfg_in.execution_type == "MOC_OR_BUFFERED_LIMIT"
    assert cfg_in.limit_buffer_pct == 0.002

    # US
    cfg_us = MarketConfig.load("US")
    assert cfg_us.trading_timezone == "America/New_York"
    assert cfg_us.open_time == "09:30"
    assert cfg_us.close_time == "16:00"
    assert cfg_us.pre_market_scan == "15:15"
    assert cfg_us.rebalance_dispatch == "15:45"
    assert cfg_us.order_cutoff == "15:55"
    assert cfg_us.execution_type == "MOC_OR_BUFFERED_LIMIT"
    assert cfg_us.limit_buffer_pct == 0.002


def test_github_workflow_daily_schedule_codification():
    """Asserts that .github/workflows/daily_trading_bot.yml contains the exact cron triggers."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    wf_path = os.path.join(root_dir, ".github", "workflows", "daily_trading_bot.yml")
    assert os.path.isfile(wf_path), "daily_trading_bot.yml must exist"

    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify India cron: 09:45 UTC = 3:15 PM IST
    assert "45 09 * * 1-5" in content, "Workflow must schedule India rebalance at 09:45 UTC (15:15 IST)"
    # Verify US cron: 19:45 UTC = 3:45 PM EDT
    assert "45 19 * * 1-5" in content, "Workflow must schedule US rebalance at 19:45 UTC (15:45 EDT)"

    # Verify target market selector step exists
    assert "TARGET_MARKET" in content
    assert "TRADING_MARKET" in content


def test_dual_pod_cloud_trader_official_schedule_codification():
    """
    Asserts that .github/workflows/dual_pod_cloud_trader.yml contains the canonical
    4-phase schedule for Dual-Pod autonomous trading across India and US markets.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    wf_path = os.path.join(root_dir, ".github", "workflows", "dual_pod_cloud_trader.yml")
    assert os.path.isfile(wf_path), "dual_pod_cloud_trader.yml must exist"

    with open(wf_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 03:46 UTC = 09:16 IST (Mon-Fri) - India Market Open Execution
    assert "46 3 * * 1-5" in content, "Workflow must schedule India open execution at 03:46 UTC (09:16 IST)"
    # 2. 10:05 UTC = 15:35 IST (Mon-Fri) - India Market Close Scan
    assert "5 10 * * 1-5" in content, "Workflow must schedule India close scan at 10:05 UTC (15:35 IST)"
    # 3. 14:31 UTC = 09:31 EST (Mon-Fri) - US Market Open Execution
    assert "31 14 * * 1-5" in content, "Workflow must schedule US open execution at 14:31 UTC (09:31 EST)"
    # 4. 21:05 UTC = 16:05 EST (Mon-Fri) - US Market Close Scan
    assert "5 21 * * 1-5" in content, "Workflow must schedule US close scan at 21:05 UTC (16:05 EST)"

    # Verify dedicated concurrency lock on state
    assert "group: trading-state" in content, "Must participate in trading-state concurrency group"
    assert "cancel-in-progress: false" in content, "Must not cancel in progress state updates"

