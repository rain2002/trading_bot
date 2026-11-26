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


def test_active_workflows_schedule_and_concurrency():
    """Asserts that the active production and shadow workflows have valid schedules and locks."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # 1. Active Gate B India Multi-Bot pipeline (10:43 UTC Mon-Fri)
    india_wf = os.path.join(root_dir, ".github", "workflows", "daily_multi_bot_pipeline.yml")
    assert os.path.isfile(india_wf), "daily_multi_bot_pipeline.yml must exist"
    with open(india_wf, "r", encoding="utf-8") as f:
        india_content = f.read()
    assert "43 10 * * 1-5" in india_content
    assert "group: trading-state" in india_content
    assert "cancel-in-progress: false" in india_content

    # 2. Active US Shadow Scan & Execute workflows
    us_scan_wf = os.path.join(root_dir, ".github", "workflows", "shadow_us_scan.yml")
    us_exec_wf = os.path.join(root_dir, ".github", "workflows", "shadow_us_execute.yml")
    assert os.path.isfile(us_scan_wf), "shadow_us_scan.yml must exist"
    assert os.path.isfile(us_exec_wf), "shadow_us_execute.yml must exist"

