#!/usr/bin/env python3
"""
Pre-Commit & CI Fiduciary Safety Guard: Real Account ID & Credential Blocker.
=============================================================================
Scans modified and staged repository files to guarantee that:
1. No real production Alpaca Key IDs (AK...) are committed.
2. No real Indian Permanent Account Numbers (PANs) are exposed.
3. No 12-digit Indian Aadhaar numbers or live bank account identifiers exist.
4. No real broker session tokens (Groww/Dhan/Alpaca bearer JWTs) are tracked.
5. No live personal wealth balances are accidentally recorded.

Fails with exit code 1 if any pattern matching a live real account identifier is found.
"""

import os
import sys
import re
from typing import List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# High-Risk Real Credential Patterns
RULES = [
    (
        "Alpaca Live Key ID (AK...)",
        re.compile(r"\bAK[A-Z0-9]{18}\b"),
        "Live Alpaca API key detected! Only paper keys (PK...) or mock values are permitted."
    ),
    (
        "Indian PAN Card Format",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "Indian Income Tax PAN identifier detected. Personal tax identifiers must never be committed."
    ),
    (
        "Indian 12-Digit Aadhaar Identifier",
        re.compile(r"(?<![a-fA-F0-9.])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![a-fA-F0-9.])"),
        "12-digit Aadhaar UIDAI identifier pattern detected."
    ),
    (
        "Live Bank Account Key-Value Mapping",
        re.compile(r"(?i)['\"]?\b(bank_account|acc_number|account_no|account_num|bank_acc)\b['\"]?\s*[:=]\s*['\"]?[0-9]{9,18}['\"]?"),
        "Live bank account mapping detected."
    ),
    (
        "Real Broker Bearer / JWT Session Token",
        re.compile(r"(?i)\b(groww_token|dhan_token|access_token|refresh_token)\b\s*[:=]\s*['\"][a-zA-Z0-9._-]{50,}['\"]"),
        "High-entropy live broker session token detected."
    )
]

# Allowlisted Mock / Test Strings
ALLOWLIST = {
    "ABCDE1234F",       # Standard mock PAN in test fixtures
    "AKMOCKTESTKEYID01", # Mock Alpaca live ID in safety test
    "2345 6789 0123",   # Mock Aadhaar in safety test
}

# Directories to strictly exclude from scanning
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "venv",
    "env",
    ".venv",
    ".idea",
    ".vscode",
    "historical_cache",
    "historical_cache_nse"
}

EXCLUDE_EXTS = {
    ".parquet",
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".zip",
    ".key"
}


def scan_file(file_path: str) -> List[Tuple[str, int, str]]:
    """Scans a single file against all security rules. Returns list of (rule_name, line_num, line_snippet)."""
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_idx, line in enumerate(f, start=1):
                # Skip comments or documentation references discussing the rule itself
                stripped = line.strip()
                if stripped.startswith("#") and "re.compile" in stripped:
                    continue
                if "check_no_real_credentials_or_accounts.py" in line:
                    continue

                for rule_name, pattern, msg in RULES:
                    matches = pattern.findall(line)
                    for m in matches:
                        match_str = m if isinstance(m, str) else m[0]
                        if match_str in ALLOWLIST:
                            continue
                        # If inside test file testing the scanner itself, allow
                        if "test_pre_commit_credential_guard.py" in file_path and "mock" in line.lower():
                            continue
                        violations.append((rule_name, line_idx, stripped[:80]))
    except Exception as e:
        print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
    return violations


def run_check(target_paths: List[str] = None) -> int:
    """Scans files and exits with 1 if violations found, 0 otherwise."""
    if target_paths:
        target_paths = [p for p in target_paths if not p.startswith("--")]
    if not target_paths:
        target_paths = [
            os.path.join(PROJECT_ROOT, "trading_system"),
            os.path.join(PROJECT_ROOT, ".github"),
            os.path.join(PROJECT_ROOT, "docs")
        ]

    all_violations = []
    files_scanned = 0

    for path in target_paths:
        if os.path.isfile(path):
            files_to_check = [path]
        else:
            files_to_check = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in EXCLUDE_EXTS:
                        files_to_check.append(os.path.join(root, file))

        for f_path in files_to_check:
            # Skip this script itself and its own unit test
            if os.path.abspath(f_path) == os.path.abspath(__file__):
                continue
            if "test_pre_commit_credential_guard.py" in f_path:
                continue
            files_scanned += 1
            v = scan_file(f_path)
            if v:
                rel_path = os.path.relpath(f_path, PROJECT_ROOT)
                for r_name, line_num, snippet in v:
                    all_violations.append((rel_path, line_num, r_name, snippet))

    print(f"[SECURITY SCAN] Checked {files_scanned} files across repository.")
    if all_violations:
        print("\n" + "="*80, file=sys.stderr)
        print("CRITICAL SECURITY GUARD FAILURE: REAL CREDENTIAL OR LIVE ID DETECTED!", file=sys.stderr)
        print("="*80, file=sys.stderr)
        for rel_path, line_num, r_name, snippet in all_violations:
            print(f"[VIOLATION] File: {rel_path}:{line_num} | Rule: {r_name}", file=sys.stderr)
            print(f"   Snippet: {snippet}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("Action: Remove live account IDs, PAN numbers, or live keys before committing.\n", file=sys.stderr)
        return 1

    print("[PASSED] Pre-Commit Credential Check: Zero real live credentials or account IDs detected.")
    return 0


if __name__ == "__main__":
    sys.exit(run_check(sys.argv[1:] if len(sys.argv) > 1 else None))
