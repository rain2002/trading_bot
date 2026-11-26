"""
Phase 5 S2 Pre-Registered Re-Run on Full-Panel Corrected Corporate Actions (V2)
==============================================================================
Runs ONE clean evaluation of Phase 5 Candidate S2 strictly using the existing
simulate_strategy_s2 / GateEvaluator engine over nse_corporate_actions_v2.csv.
Preserves V1 protocol seals & results untouched while outputting:
  - trading_system/data/phase5_s2_v2_corrected_results.json
"""

import os
import sys
import json
import hashlib

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import trading_system.app.data.corporate_actions as ca_mod
import trading_system.scripts.run_phase5_nse_whole_market_gate_a as p5_mod

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
CA_V2_CSV = os.path.join(DATA_DIR, "nse_corporate_actions_v2.csv")
RESULTS_V2_JSON = os.path.join(DATA_DIR, "phase5_s2_v2_corrected_results.json")


def main():
    if not os.path.exists(CA_V2_CSV):
        raise FileNotFoundError(f"Missing versioned corporate actions file: {CA_V2_CSV}")

    # Point corporate actions loader to versioned V2 audited CSV (clearing cache)
    ca_mod.CORPORATE_ACTIONS_CSV = CA_V2_CSV
    ca_mod._ACTIONS_CACHE = None
    actions = ca_mod.load_audited_corporate_actions(CA_V2_CSV)
    ca_sha = hashlib.sha256(open(CA_V2_CSV, "rb").read()).hexdigest()

    # Point Phase 5 runner output to dedicated V2 ledger with honest N = 86 cumulative trials
    p5_mod.RESULTS_JSON_PATH = RESULTS_V2_JSON
    p5_mod.CUMULATIVE_N = 86

    print("=" * 85)
    print(f"PHASE 5 S2 V2 RE-RUN (CA_V2 events={len(actions)}, SHA={ca_sha[:16]}..., N=86)")
    print("=" * 85)

    p5_mod.run_phase5_gate_a()

    # Stamp V2 metadata onto results file
    if os.path.exists(RESULTS_V2_JSON):
        with open(RESULTS_V2_JSON, "r", encoding="utf-8") as f:
            res = json.load(f)
        res["corporate_actions_version"] = "nse_corporate_actions_v2.csv"
        res["corporate_actions_events_count"] = len(actions)
        res["corporate_actions_sha256"] = ca_sha
        with open(RESULTS_V2_JSON, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
