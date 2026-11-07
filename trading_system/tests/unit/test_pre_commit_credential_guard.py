"""
Unit Tests for Pre-Commit Credential Guard.
===========================================
Verifies that check_no_real_credentials_or_accounts.py properly rejects:
1. Real Alpaca live keys (AK...).
2. Indian Income Tax PAN numbers.
3. Live bank account assignments.
4. Real bearer session tokens.
And allows clean code/configs to pass.
"""

import os
import tempfile
import pytest
from trading_system.scripts.check_no_real_credentials_or_accounts import scan_file, run_check


def test_credential_guard_clean_file_passes():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as f:
        f.write("# Clean test file\n")
        f.write("ALPACA_PAPER_KEY = 'PK1234567890123456'\n")
        f.write("MAX_CAPITAL = 80000.0\n")
        temp_path = f.name

    try:
        violations = scan_file(temp_path)
        assert len(violations) == 0, f"Expected 0 violations, got {violations}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_credential_guard_detects_real_alpaca_live_key():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as f:
        # A live Alpaca key starts with AK followed by 18 alphanumeric characters
        f.write("LIVE_KEY = 'AK987654321098765432'\n")
        temp_path = f.name

    try:
        violations = scan_file(temp_path)
        assert len(violations) >= 1
        assert any(v[0] == "Alpaca Live Key ID (AK...)" for v in violations)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_credential_guard_detects_real_pan_card():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as f:
        # 5 letters, 4 digits, 1 letter
        f.write("CLIENT_PAN = 'BZQPR9482L'\n")
        temp_path = f.name

    try:
        violations = scan_file(temp_path)
        assert len(violations) >= 1
        assert any(v[0] == "Indian PAN Card Format" for v in violations)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_credential_guard_detects_bank_account_assignment():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as f:
        f.write("user_profile = {'bank_account': '50100482910482'}\n")
        temp_path = f.name

    try:
        violations = scan_file(temp_path)
        assert len(violations) >= 1
        assert any("Bank Account" in v[0] for v in violations)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
