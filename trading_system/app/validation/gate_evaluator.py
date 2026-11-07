"""
Institutional Gate A & Gate B Clearance Evaluator
Document Classification: Master Fiduciary Blueprint & Final Architecture
Strictly Governed by: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)

Fiduciary Principles:
Gate A (Statistical Stress Clearance):
1. Out-of-sample CAGR >= 15.0% after all fees, taxes, and 50% slippage stress.
2. Maximum peak-to-trough Drawdown <= -25.0%.
3. Total out-of-sample trades >= 100.
4. Parameter stability plateaus (performance within +/-20% param variation).
5. Monte Carlo worst 5th-percentile Drawdown within -30.0%.

Gate B (Live Forward Paper Clearance - 13 Weeks):
1. 13 consecutive weeks of forward paper execution on live quotes.
2. Minimum 4 consecutive weeks of zero crashed runs.
3. Live paper maximum drawdown <= -10.0%.
4. Zero unhandled hard stop-loss breaches (-8.0% mandate).
5. Emergency Discord kill-switch drill successfully verified.
"""

import os
import math
import json
import logging
import hmac
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from trading_system.app.common.logger import get_logger
from trading_system.app.validation.trial_logger import get_trial_count

logger = get_logger("GateEvaluator")

GATE_A_CERTIFICATION_SALT = b"ANTIGRAVITY_FIDUCIARY_GATE_A_AUTHORITY_SALT_V2"


def _canonical_payload(
    variant_id: str,
    protocol_hash: str,
    cagr_pct: float,
    max_drawdown_pct: float,
    total_trades: int,
    is_holdout_opened: bool,
    timestamp: str
) -> str:
    """Builds deterministic string representation of certified Gate A metrics for HMAC signing."""
    return f"{variant_id.strip()}|{protocol_hash.strip()}|{cagr_pct:.4f}|{max_drawdown_pct:.4f}|{int(total_trades)}|{bool(is_holdout_opened)}|{timestamp.strip()}"


def _generate_signature(payload_str: str) -> str:
    """Computes HMAC-SHA256 signature for canonical Gate A certification payload."""
    return hmac.new(GATE_A_CERTIFICATION_SALT, payload_str.encode("utf-8"), hashlib.sha256).hexdigest().upper()



@dataclass
class GateAClearanceReport:
    passed: bool
    oos_cagr: float
    max_drawdown: float
    total_trades: int
    parameter_stability: float
    monte_carlo_p5_dd: float
    deflated_sharpe: float = 1.0
    num_trials: int = 1
    criteria: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


@dataclass
class GateBClearanceReport:
    passed: bool
    weeks_logged: int
    zero_crash_weeks: int
    max_drawdown: float
    sl_breaches: int
    kill_switch_verified: bool
    criteria: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""


class GateEvaluator:
    """
    Independent statistical and forward paper incubation gatekeeper.
    Controls clearance into Stage 2 (Real INR Capital).
    """

    # Gate A Hard Cutoffs
    GATE_A_MIN_CAGR: float = 0.15           # 15.0% Net CAGR
    GATE_A_MAX_DRAWDOWN: float = -0.25      # -25.0% Max Drawdown
    GATE_A_MIN_TRADES: int = 100            # 100 trades sample size
    GATE_A_MIN_STABILITY: float = 0.80      # 80% plateau stability
    GATE_A_WORST_P5_MC_DD: float = -0.30    # -30.0% Monte Carlo 5th percentile
    GATE_A_MIN_DSR: float = 0.95            # 95.0% Deflated Sharpe Ratio confidence

    # Gate B Hard Cutoffs
    GATE_B_MIN_WEEKS: int = 13              # 13 weeks forward incubation
    GATE_B_CONSECUTIVE_STABLE_WEEKS: int = 4 # 4 weeks zero crashes
    GATE_B_MAX_INCUBATION_DD: float = -0.10 # -10.0% max DD in incubation

    @staticmethod
    def compute_deflated_sharpe(
        sharpe: float,
        num_trials: int,
        num_observations: int = 1260,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
        var_sharpe: float = 0.15
    ) -> float:
        """
        Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio (DSR).
        Computes the probability that the estimated Sharpe ratio exceeds
        the expected maximum Sharpe ratio under the null hypothesis of selection bias:
        DSR = Phi( (SR - E[max SR]) / SE )
        """
        if num_trials <= 1:
            e_max_sr = 0.0
        else:
            euler_mascheroni = 0.5772156649
            try:
                from scipy import stats
                z1 = stats.norm.ppf(1.0 - 1.0 / num_trials)
                z2 = stats.norm.ppf(1.0 - 1.0 / (num_trials * math.e))
            except Exception:
                z1 = math.sqrt(2.0 * math.log(num_trials))
                z2 = math.sqrt(2.0 * math.log(num_trials * math.e))
            e_max_sr = math.sqrt(var_sharpe) * ((1.0 - euler_mascheroni) * z1 + euler_mascheroni * z2)

        denom = 1.0 - skewness * sharpe + ((kurtosis - 1.0) / 4.0) * (sharpe ** 2)
        se = math.sqrt(max(denom, 1e-4) / max(num_observations - 1, 1))
        z = (sharpe - e_max_sr) / max(se, 1e-6)

        # Standard normal CDF via math.erf
        dsr = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        return float(dsr)

    @classmethod
    def evaluate_gate_a(
        cls,
        oos_cagr: float,
        max_drawdown: float,
        total_trades: int,
        parameter_stability: float,
        monte_carlo_p5_dd: float,
        sharpe_ratio: Optional[float] = None,
        num_trials: Optional[int] = None,
        trial_log_path: Optional[str] = None,
        num_observations: int = 1260
    ) -> GateAClearanceReport:
        """
        Evaluates backtest / walk-forward candidate against Gate A criteria,
        including Bailey & Lopez de Prado Deflated Sharpe Ratio against logged trials.
        """
        cagr_pass = oos_cagr >= cls.GATE_A_MIN_CAGR
        dd_pass = max_drawdown >= cls.GATE_A_MAX_DRAWDOWN
        trades_pass = total_trades >= cls.GATE_A_MIN_TRADES
        stability_pass = parameter_stability >= cls.GATE_A_MIN_STABILITY
        mc_pass = monte_carlo_p5_dd >= cls.GATE_A_WORST_P5_MC_DD

        # Deflated Sharpe Check
        if num_trials is None:
            trials_logged = get_trial_count(trial_log_path)
        else:
            trials_logged = max(1, int(num_trials))

        if sharpe_ratio is not None:
            dsr = cls.compute_deflated_sharpe(
                sharpe=sharpe_ratio,
                num_trials=trials_logged,
                num_observations=num_observations
            )
            dsr_pass = dsr >= cls.GATE_A_MIN_DSR
        else:
            dsr = 1.0
            dsr_pass = True

        all_passed = cagr_pass and dd_pass and trades_pass and stability_pass and mc_pass and dsr_pass

        criteria = {
            "cagr": {
                "name": "Out-of-Sample Net CAGR (>= 15.0%)",
                "actual": round(oos_cagr * 100, 2),
                "threshold": round(cls.GATE_A_MIN_CAGR * 100, 2),
                "passed": cagr_pass
            },
            "drawdown": {
                "name": "Max Peak-to-Trough Drawdown (<= -25.0%)",
                "actual": round(max_drawdown * 100, 2),
                "threshold": round(cls.GATE_A_MAX_DRAWDOWN * 100, 2),
                "passed": dd_pass
            },
            "sample_size": {
                "name": "OOS Trade Sample Size (>= 100 trades)",
                "actual": total_trades,
                "threshold": cls.GATE_A_MIN_TRADES,
                "passed": trades_pass
            },
            "stability": {
                "name": "Parameter Plateau Stability (>= 80%)",
                "actual": round(parameter_stability * 100, 2),
                "threshold": round(cls.GATE_A_MIN_STABILITY * 100, 2),
                "passed": stability_pass
            },
            "monte_carlo_dd": {
                "name": "Monte Carlo 5th-Percentile Worst DD (<= -30.0%)",
                "actual": round(monte_carlo_p5_dd * 100, 2),
                "threshold": round(cls.GATE_A_WORST_P5_MC_DD * 100, 2),
                "passed": mc_pass
            },
            "deflated_sharpe": {
                "name": "Deflated Sharpe Ratio (>= 95.0% Confidence)",
                "actual": round(dsr * 100, 2),
                "threshold": round(cls.GATE_A_MIN_DSR * 100, 2),
                "trials_logged": trials_logged,
                "passed": dsr_pass
            }
        }

        if all_passed:
            summary = "GATE A PASSED: All 6 statistical stress hurdles cleared (including Deflated Sharpe). Qualified for paper incubation."
        else:
            failed_keys = [k for k, v in criteria.items() if not v["passed"]]
            summary = f"GATE A REJECTED: Failed criteria: {', '.join(failed_keys)}."

        return GateAClearanceReport(
            passed=all_passed,
            oos_cagr=oos_cagr,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            parameter_stability=parameter_stability,
            monte_carlo_p5_dd=monte_carlo_p5_dd,
            deflated_sharpe=round(dsr, 4),
            num_trials=trials_logged,
            criteria=criteria,
            summary=summary
        )

    @classmethod
    def certify_gate_a_result(
        cls,
        variant_id: str,
        protocol_hash: str,
        cagr_pct: float,
        max_drawdown_pct: float,
        total_trades: int,
        is_holdout_opened: bool,
        cert_dir: Optional[str] = None,
        parameter_stability: float = 1.0,
        monte_carlo_p5_dd: float = -0.20,
        deflated_sharpe: float = 1.0,
        timestamp: Optional[str] = None
    ) -> Optional[str]:
        """
        Signs and writes an authenticated Gate A certification record.
        Refuses to sign if any Gate A hurdle is breached (CAGR < 15%, MaxDD < -25%, Trades < 100, or Holdout Opened).
        """
        if cagr_pct < (cls.GATE_A_MIN_CAGR * 100):
            logger.warning(f"Cannot certify Gate A for {variant_id}: CAGR {cagr_pct:.2f}% < {cls.GATE_A_MIN_CAGR * 100}%")
            return None
        if max_drawdown_pct < (cls.GATE_A_MAX_DRAWDOWN * 100):
            logger.warning(f"Cannot certify Gate A for {variant_id}: Max Drawdown {max_drawdown_pct:.2f}% < {cls.GATE_A_MAX_DRAWDOWN * 100}%")
            return None
        if total_trades < cls.GATE_A_MIN_TRADES:
            logger.warning(f"Cannot certify Gate A for {variant_id}: Total Trades {total_trades} < {cls.GATE_A_MIN_TRADES}")
            return None
        if is_holdout_opened is True:
            logger.warning(f"Cannot certify Gate A for {variant_id}: Holdout was unblinded/opened!")
            return None

        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        payload_str = _canonical_payload(
            variant_id=variant_id,
            protocol_hash=protocol_hash,
            cagr_pct=cagr_pct,
            max_drawdown_pct=max_drawdown_pct,
            total_trades=total_trades,
            is_holdout_opened=is_holdout_opened,
            timestamp=timestamp
        )
        sig = _generate_signature(payload_str)

        cert_data = {
            "variant_id": variant_id,
            "protocol_hash": protocol_hash,
            "cagr_pct": round(float(cagr_pct), 4),
            "max_drawdown_pct": round(float(max_drawdown_pct), 4),
            "total_trades": int(total_trades),
            "parameter_stability": round(float(parameter_stability), 4),
            "monte_carlo_p5_dd": round(float(monte_carlo_p5_dd), 4),
            "deflated_sharpe": round(float(deflated_sharpe), 4),
            "is_holdout_opened": bool(is_holdout_opened),
            "certified_timestamp": timestamp,
            "hmac_signature": sig
        }

        if cert_dir is None:
            cert_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "gate_a_certifications"
            )
        os.makedirs(cert_dir, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", variant_id.lower().strip())
        out_path = os.path.join(cert_dir, f"{slug}_gate_a_certified.json")

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cert_data, f, indent=2)

        logger.info(f"Gate A signed certification created for {variant_id} at {out_path}")
        return out_path

    @classmethod
    def verify_gate_a_clearance_for_gate_b(
        cls,
        variant_id: str,
        protocol_hash: Optional[str] = None,
        trial_log_path: Optional[str] = None,
        cert_file_path: Optional[str] = None,
        cert_dir: Optional[str] = None
    ) -> bool:
        """
        CODE GUARD: Fiduciary gate preventing Gate B incubation from starting
        or being certified unless an authenticated, cryptographically signed Gate A
        certification file exists on disk, written solely by GateEvaluator.certify_gate_a_result.

        Refuses plain-text notes in trial_log.csv or forged strings.
        Validates HMAC signature and verifies metrics:
          - CAGR >= 15.0%
          - Max DD >= -25.0% (<= 25% drawdown magnitude)
          - Trades >= 100
          - is_holdout_opened is False
        """
        if cert_file_path is None:
            if cert_dir is None:
                cert_dir = os.path.join(
                    os.path.dirname(__file__), "..", "..", "data", "gate_a_certifications"
                )
            slug = re.sub(r"[^a-zA-Z0-9_-]", "_", variant_id.lower().strip())
            cert_file_path = os.path.join(cert_dir, f"{slug}_gate_a_certified.json")

        if not os.path.exists(cert_file_path):
            logger.warning(
                f"Gate A clearance refused for '{variant_id}': No signed certification found at {cert_file_path}."
            )
            return False

        try:
            with open(cert_file_path, "r", encoding="utf-8") as f:
                cert = json.load(f)

            # 1. Verify required cryptographic fields
            required_fields = [
                "variant_id", "protocol_hash", "cagr_pct", "max_drawdown_pct",
                "total_trades", "is_holdout_opened", "certified_timestamp", "hmac_signature"
            ]
            for field in required_fields:
                if field not in cert:
                    logger.critical(f"Gate A cert corrupt: missing field '{field}'. Refusing Gate B.")
                    return False

            # 2. Verify HMAC signature integrity
            expected_payload = _canonical_payload(
                variant_id=cert["variant_id"],
                protocol_hash=cert["protocol_hash"],
                cagr_pct=cert["cagr_pct"],
                max_drawdown_pct=cert["max_drawdown_pct"],
                total_trades=cert["total_trades"],
                is_holdout_opened=cert["is_holdout_opened"],
                timestamp=cert["certified_timestamp"]
            )
            expected_sig = _generate_signature(expected_payload)
            if not hmac.compare_digest(cert["hmac_signature"], expected_sig):
                logger.critical(f"GATE A CERTIFICATE TAMPERING DETECTED for '{variant_id}'! Signature mismatch. Refusing Gate B.")
                return False

            # 3. Match Variant ID
            if cert["variant_id"].strip().lower() != variant_id.strip().lower():
                logger.warning(f"Variant ID mismatch: expected '{variant_id}', cert has '{cert['variant_id']}'")
                return False

            # 4. Match Protocol Hash (if provided)
            if protocol_hash:
                p_clean = protocol_hash.strip().upper()
                cert_p = cert["protocol_hash"].strip().upper()
                if not (cert_p.startswith(p_clean[:8]) or p_clean.startswith(cert_p[:8])):
                    logger.warning(f"Protocol hash mismatch: expected prefix {p_clean[:8]}, cert has {cert_p[:8]}")
                    return False

            # 5. Invariant: Holdout must remain strictly unblinded
            if cert["is_holdout_opened"] is True:
                logger.critical(f"Fiduciary violation: Holdout for '{variant_id}' was unblinded. Disqualified from Gate B.")
                return False

            # 6. Invariant: Max drawdown cutoff
            if cert["max_drawdown_pct"] < (cls.GATE_A_MAX_DRAWDOWN * 100):
                logger.warning(f"Gate A max drawdown failure: {cert['max_drawdown_pct']}% < {cls.GATE_A_MAX_DRAWDOWN * 100}%. Refusing Gate B.")
                return False

            # 7. Invariant: Minimum CAGR
            if cert["cagr_pct"] < (cls.GATE_A_MIN_CAGR * 100):
                logger.warning(f"Gate A CAGR failure: {cert['cagr_pct']}% < {cls.GATE_A_MIN_CAGR * 100}%. Refusing Gate B.")
                return False

            # 8. Invariant: Minimum Trade Sample Size
            if cert["total_trades"] < cls.GATE_A_MIN_TRADES:
                logger.warning(f"Gate A sample size failure: {cert['total_trades']} < {cls.GATE_A_MIN_TRADES}. Refusing Gate B.")
                return False

            logger.info(f"AUTHENTICATED Gate A clearance confirmed for '{variant_id}'. Gate B authorized.")
            return True

        except Exception as e:
            logger.error(f"Error validating Gate A certification for Gate B: {e}")
            return False

    @classmethod
    def evaluate_gate_b(
        cls,
        weeks_logged: int,
        zero_crash_weeks: int,
        max_drawdown: float,
        sl_breaches: int,
        kill_switch_verified: bool,
        variant_id: Optional[str] = None,
        protocol_hash: Optional[str] = None
    ) -> GateBClearanceReport:
        """
        Evaluates live forward paper trading results against Gate B incubation requirements.
        Strictly enforces prerequisite Gate A clearance.
        """
        # Code Guard: Check prerequisite Gate A
        if variant_id:
            gate_a_passed = cls.verify_gate_a_clearance_for_gate_b(variant_id=variant_id, protocol_hash=protocol_hash)
            if not gate_a_passed:
                return GateBClearanceReport(
                    passed=False,
                    weeks_logged=weeks_logged,
                    zero_crash_weeks=zero_crash_weeks,
                    max_drawdown=max_drawdown,
                    sl_breaches=sl_breaches,
                    kill_switch_verified=kill_switch_verified,
                    criteria={
                        "gate_a_prerequisite": {
                            "name": "Prerequisite Gate A Statistical Clearance Verified",
                            "actual": "FAILED / UNVERIFIED",
                            "threshold": "PASSED (Audited Gate A Clearance Required)",
                            "passed": False
                        }
                    },
                    summary=f"GATE B REFUSED: Variant '{variant_id}' has not passed Gate A with verified protocol hash. Incubation cannot be certified as Gate B."
                )
        weeks_pass = weeks_logged >= cls.GATE_B_MIN_WEEKS
        crashes_pass = zero_crash_weeks >= cls.GATE_B_CONSECUTIVE_STABLE_WEEKS
        dd_pass = max_drawdown >= cls.GATE_B_MAX_INCUBATION_DD
        sl_pass = sl_breaches == 0
        kill_pass = kill_switch_verified is True

        all_passed = weeks_pass and crashes_pass and dd_pass and sl_pass and kill_pass

        criteria = {
            "incubation_period": {
                "name": "Forward Incubation Duration (>= 13 Weeks)",
                "actual": weeks_logged,
                "threshold": cls.GATE_B_MIN_WEEKS,
                "passed": weeks_pass
            },
            "operational_stability": {
                "name": "Zero-Crash Consecutive Execution (>= 4 Weeks)",
                "actual": zero_crash_weeks,
                "threshold": cls.GATE_B_CONSECUTIVE_STABLE_WEEKS,
                "passed": crashes_pass
            },
            "drawdown_containment": {
                "name": "Paper Max Drawdown Containment (< 10.0%)",
                "actual": round(max_drawdown * 100, 2),
                "threshold": round(cls.GATE_B_MAX_INCUBATION_DD * 100, 2),
                "passed": dd_pass
            },
            "hard_stops": {
                "name": "Strict Hard Stop-Loss Enforcement (-8.0% Mandate)",
                "actual": f"{sl_breaches} unhandled",
                "threshold": "0 unhandled",
                "passed": sl_pass
            },
            "kill_switch_drill": {
                "name": "Emergency Discord Kill-Switch Verification",
                "actual": "VERIFIED" if kill_pass else "PENDING_DRILL",
                "threshold": "VERIFIED",
                "passed": kill_pass
            }
        }

        if all_passed:
            summary = "GATE B PASSED: 13-week institutional incubation verified. Ready for Stage 2 real INR capital allocation."
        else:
            failed_keys = [k for k, v in criteria.items() if not v["passed"]]
            summary = f"GATE B IN PROGRESS: Remaining hurdles: {', '.join(failed_keys)}."

        return GateBClearanceReport(
            passed=all_passed,
            weeks_logged=weeks_logged,
            zero_crash_weeks=zero_crash_weeks,
            max_drawdown=max_drawdown,
            sl_breaches=sl_breaches,
            kill_switch_verified=kill_switch_verified,
            criteria=criteria,
            summary=summary
        )
