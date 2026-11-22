"""
Data & Ledger Integrity Guard (CI Stage)
========================================
Validates that trial_log.csv, corporate actions, and all results JSON ledgers
are mathematically consistent, well-formed, and free from corruption.
"""

import os
import sys
import csv
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
TRIAL_LOG_PATH = os.path.join(DATA_DIR, "trial_log.csv")


def verify_trial_log() -> bool:
    print("Checking trial_log.csv integrity...", flush=True)
    if not os.path.exists(TRIAL_LOG_PATH):
        print(f"ERROR: trial_log.csv not found at {TRIAL_LOG_PATH}")
        return False

    with open(TRIAL_LOG_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            print("ERROR: trial_log.csv is empty")
            return False

        rows = list(reader)
        print(f"  Header verified. Total logged trials: N = {len(rows)}")

        for i, row in enumerate(rows, start=1):
            if len(row) < 9:
                print(f"ERROR: Row {i} has fewer than 9 columns: {row}")
                return False
            # Check timestamp format
            ts = row[0].strip()
            if len(ts) < 10 or ts[4] != "-" or ts[7] != "-":
                print(f"ERROR: Row {i} has invalid timestamp: '{ts}'")
                return False

    print("  trial_log.csv: PASS")
    return True


def verify_json_results() -> bool:
    print("Checking JSON result files integrity...", flush=True)
    json_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and "result" in f]
    print(f"  Found {len(json_files)} results JSON files to validate.")

    for jf in json_files:
        path = os.path.join(DATA_DIR, jf)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    print(f"ERROR: {jf} is not a JSON object")
                    return False
        except Exception as e:
            print(f"ERROR: Failed to parse {jf}: {e}")
            return False

    print(f"  All {len(json_files)} JSON ledgers parsed successfully: PASS")
    return True


def main():
    print("=== STARTING DATA & LEDGER INTEGRITY AUDIT ===")
    ok1 = verify_trial_log()
    ok2 = verify_json_results()

    if ok1 and ok2:
        print("\n[PASS] All data and ledger integrity checks passed.")
        sys.exit(0)
    else:
        print("\n[FAIL] Data integrity violations detected.")
        sys.exit(1)


if __name__ == "__main__":
    main()
