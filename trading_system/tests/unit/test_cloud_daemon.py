import pytest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from trading_system.scripts.cloud_daemon import check_and_trigger


def test_cloud_daemon_triggers_india_open():
    # 09:16 IST on a Wednesday (2026-11-04 03:46 UTC)
    t = datetime(2026, 11, 4, 3, 46, 0, tzinfo=ZoneInfo("UTC"))
    state = {"completed_jobs": {}}

    with patch("trading_system.scripts.cloud_daemon.run_pod_command") as mock_run:
        res = check_and_trigger(t, state)
        assert res is True
        mock_run.assert_called_once_with(phase="execute", pod="india")
        assert "india_execute_2026-11-04" in state["completed_jobs"]

        # Run again with same timestamp -> must NOT re-trigger (idempotent)
        res_second = check_and_trigger(t, state)
        assert res_second is False
        assert mock_run.call_count == 1


def test_cloud_daemon_triggers_india_close():
    # 15:35 IST on a Wednesday (2026-11-04 10:05 UTC)
    t = datetime(2026, 11, 4, 10, 5, 0, tzinfo=ZoneInfo("UTC"))
    state = {"completed_jobs": {}}

    with patch("trading_system.scripts.cloud_daemon.run_pod_command") as mock_run:
        res = check_and_trigger(t, state)
        assert res is True
        mock_run.assert_called_once_with(phase="scan", pod="india")
        assert "india_scan_2026-11-04" in state["completed_jobs"]


def test_cloud_daemon_triggers_us_open():
    # 09:31 US/Eastern on a Wednesday (Standard Time UTC-5 -> 14:31 UTC)
    t = datetime(2026, 11, 4, 14, 31, 0, tzinfo=ZoneInfo("UTC"))
    state = {"completed_jobs": {}}

    with patch("trading_system.scripts.cloud_daemon.run_pod_command") as mock_run:
        res = check_and_trigger(t, state)
        assert res is True
        mock_run.assert_called_once_with(phase="execute", pod="us")
        assert "us_execute_2026-11-04" in state["completed_jobs"]


def test_cloud_daemon_triggers_us_close():
    # 16:05 US/Eastern on a Wednesday (Standard Time UTC-5 -> 21:05 UTC)
    t = datetime(2026, 11, 4, 21, 5, 0, tzinfo=ZoneInfo("UTC"))
    state = {"completed_jobs": {}}

    with patch("trading_system.scripts.cloud_daemon.run_pod_command") as mock_run:
        res = check_and_trigger(t, state)
        assert res is True
        mock_run.assert_called_once_with(phase="scan", pod="us")
        assert "us_scan_2026-11-04" in state["completed_jobs"]


def test_cloud_daemon_weekend_no_triggers():
    # Saturday 15:35 IST (2026-11-07 10:05 UTC)
    t = datetime(2026, 11, 7, 10, 5, 0, tzinfo=ZoneInfo("UTC"))
    state = {"completed_jobs": {}}

    with patch("trading_system.scripts.cloud_daemon.run_pod_command") as mock_run:
        res = check_and_trigger(t, state)
        assert res is False
        mock_run.assert_not_called()
