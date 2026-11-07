"""
Unit Tests for Two-Factor Live Order Safety Fuse.
=================================================
Verifies that:
1. verify_live_safety_fuse() blocks live order execution when fuse file is absent.
2. Even with ALPACA_LIVE="1", AlpacaExecutionAdapter raises LiveExecutionBlockedError.
3. Placing the exact authorized passphrase trips the fuse and allows execution.
4. Tampered / incorrect passphrase in the fuse file raises LiveExecutionBlockedError.
"""

import os
import tempfile
import pytest
from unittest.mock import patch

from trading_system.app.broker.live_safety_fuse import (
    verify_live_safety_fuse,
    LiveExecutionBlockedError,
    LIVE_FUSE_FILENAME,
    EXPECTED_FUSE_PHRASE
)
from trading_system.app.execution.alpaca_live import AlpacaExecutionAdapter


def test_safety_fuse_blocks_when_file_missing(tmp_path):
    with patch("trading_system.app.broker.live_safety_fuse.find_fuse_file", return_value=None):
        with pytest.raises(LiveExecutionBlockedError) as exc_info:
            verify_live_safety_fuse("Test Broker")
        assert "CRITICAL SAFETY FUSE ENGAGED" in str(exc_info.value)


def test_safety_fuse_blocks_alpaca_live_env_variable(tmp_path):
    with patch.dict(os.environ, {"ALPACA_LIVE": "1"}):
        with patch("trading_system.app.broker.live_safety_fuse.find_fuse_file", return_value=None):
            adapter = AlpacaExecutionAdapter(api_key="mock", api_secret="mock")
            with pytest.raises(LiveExecutionBlockedError):
                adapter.submit_order({"symbol": "AAPL", "quantity": 10})


def test_safety_fuse_blocks_when_passphrase_invalid(tmp_path):
    fuse_file = tmp_path / LIVE_FUSE_FILENAME
    fuse_file.write_text("SOME_UNAUTHORIZED_STRING_OR_TYPO", encoding="utf-8")

    with patch("trading_system.app.broker.live_safety_fuse.find_fuse_file", return_value=str(fuse_file)):
        with pytest.raises(LiveExecutionBlockedError) as exc_info:
            verify_live_safety_fuse("Test Broker")
        assert "SAFETY FUSE INVALID" in str(exc_info.value)


def test_safety_fuse_passes_when_passphrase_valid(tmp_path):
    fuse_file = tmp_path / LIVE_FUSE_FILENAME
    fuse_file.write_text(EXPECTED_FUSE_PHRASE, encoding="utf-8")

    with patch("trading_system.app.broker.live_safety_fuse.find_fuse_file", return_value=str(fuse_file)):
        assert verify_live_safety_fuse("Test Broker") is True
