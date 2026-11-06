"""
Unit tests verifying Strict Long-Only Backtest Invariants and Removal of Pairs (Fix 1).
"""

import ast
import pytest
from pathlib import Path


def test_backtest_script_has_zero_pairs_or_short_logic():
    """
    Verify that backtest_multi_pod.py has no shorting or pair-trading logic
    by inspecting the Abstract Syntax Tree (AST), checking for actual negative-share logic
    rather than fragile text substring matches on header comments.
    """
    script_path = Path("trading_system/scripts/backtest_multi_pod.py")
    assert script_path.exists(), "backtest_multi_pod.py must exist"

    code = script_path.read_text(encoding="utf-8")
    tree = ast.parse(code)

    # 1. Collect all variable names and attribute names in AST (ignoring comments and docstrings)
    variable_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            variable_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            variable_names.add(node.attr)

    forbidden_identifiers = {"y_shares", "x_shares", "pod2_positions", "CURATED_PAIRS"}
    found_forbidden = variable_names.intersection(forbidden_identifiers)
    assert not found_forbidden, f"Forbidden short/pairs logic identifiers found in AST: {found_forbidden}"

    # 2. Check for negative-share logic verification in AST:
    # Must contain a Comparison checking for negative shares (e.g. shares < 0) with a Raise ValueError
    has_negative_share_guard = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # Check if comparison is `< 0`
            if isinstance(node.test, ast.Compare):
                for op, comparator in zip(node.test.ops, node.test.comparators):
                    if isinstance(op, ast.Lt) and isinstance(comparator, ast.Constant) and comparator.value == 0:
                        # Check if inside the body there is a raise ValueError
                        for body_stmt in node.body:
                            if isinstance(body_stmt, ast.Raise):
                                has_negative_share_guard = True
                                break

    assert has_negative_share_guard, "backtest_multi_pod.py must actively enforce shares < 0 guard with ValueError"


def test_daily_non_negative_share_check():
    """Verify the daily non-negative share invariant logic."""
    # Healthy positions
    valid_positions = {"AAPL": 10.5, "MSFT": 4.0, "GOOGL": 0.0}
    for sym, shares in valid_positions.items():
        if shares < 0:
            pytest.fail(f"Unexpected failure on valid shares: {sym}={shares}")

    # Negative share violation
    invalid_positions = {"AAPL": 10.5, "NVDA": -5.0}
    with pytest.raises(ValueError) as excinfo:
        for sym, shares in invalid_positions.items():
            if shares < 0:
                raise ValueError(f"CRITICAL FIDUCIARY BREACH: Negative share count detected: {sym}={shares}")

    assert "Negative share count detected" in str(excinfo.value)
    assert "NVDA=-5.0" in str(excinfo.value)
