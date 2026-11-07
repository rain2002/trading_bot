"""
Cloud Autonomous 24/7 Dual-Pod Daemon
=====================================
Runs continuously on cloud infrastructure (e.g., GCP Always-Free e2-micro).
Monitors market hours using native timezone-aware clocks (Asia/Kolkata & America/New_York).

Schedules:
  1. India Open Execution: Mon-Fri at 09:16:00 IST (executes open fills)
  2. India Close Scan:     Mon-Fri at 15:35:00 IST (scans and queues orders)
  3. US Open Execution:    Mon-Fri at 09:31:00 US/Eastern (executes open fills on Alpaca)
  4. US Close Scan:        Mon-Fri at 16:05:00 US/Eastern (scans and queues orders)

Idempotent: Records completed run timestamps to prevent duplicate runs on restarts.
"""

import os
import sys
import time
import json
import logging
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

LOG_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "cloud_daemon.log")
STATE_FILE = os.path.join(PROJECT_ROOT, "trading_system", "data", "daemon_state.json")
RUNNER_SCRIPT = os.path.join(PROJECT_ROOT, "trading_system", "scripts", "run_dual_pod_paper.py")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("CloudDaemon")


def load_daemon_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_jobs": {}}


def save_daemon_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def run_pod_command(phase: str, pod: str):
    logger.info(f"Triggering scheduled job: Phase={phase.upper()}, Pod={pod.upper()}")
    cmd = [sys.executable, RUNNER_SCRIPT, "--phase", phase, "--pod", pod]
    try:
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        logger.info(f"Job completed successfully: Phase={phase}, Pod={pod}")
        if res.stdout:
            for line in res.stdout.strip().split("\n")[-10:]:
                logger.info(f"  [output] {line}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Job failed with code {e.returncode}: {e.stderr}")


def check_and_trigger(now_utc: datetime, state: dict) -> bool:
    """
    Evaluates current time across IST and US/Eastern and executes pending routines.
    Returns True if any job was executed.
    """
    executed = False
    now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    now_us = now_utc.astimezone(ZoneInfo("America/New_York"))

    date_ist_str = now_ist.strftime("%Y-%m-%d")
    date_us_str = now_us.strftime("%Y-%m-%d")

    completed = state.setdefault("completed_jobs", {})

    # 1. India Open Execution: Mon-Fri 09:16 - 09:45 IST
    if now_ist.weekday() < 5:  # Mon=0, Fri=4
        job_key = f"india_execute_{date_ist_str}"
        if now_ist.hour == 9 and 16 <= now_ist.minute <= 45 and job_key not in completed:
            run_pod_command(phase="execute", pod="india")
            completed[job_key] = now_ist.isoformat()
            executed = True

        # 2. India Close Scan: Mon-Fri 15:35 - 16:30 IST
        job_key = f"india_scan_{date_ist_str}"
        if ((now_ist.hour == 15 and now_ist.minute >= 35) or (now_ist.hour == 16 and now_ist.minute <= 30)) and job_key not in completed:
            run_pod_command(phase="scan", pod="india")
            completed[job_key] = now_ist.isoformat()
            executed = True

    # 3. US Open Execution: Mon-Fri 09:31 - 10:00 US/Eastern
    if now_us.weekday() < 5:
        job_key = f"us_execute_{date_us_str}"
        if now_us.hour == 9 and 31 <= now_us.minute <= 59 and job_key not in completed:
            run_pod_command(phase="execute", pod="us")
            completed[job_key] = now_us.isoformat()
            executed = True

        # 4. US Close Scan: Mon-Fri 16:05 - 17:00 US/Eastern
        job_key = f"us_scan_{date_us_str}"
        if ((now_us.hour == 16 and now_us.minute >= 5) or (now_us.hour == 17 and now_us.minute == 0)) and job_key not in completed:
            run_pod_command(phase="scan", pod="us")
            completed[job_key] = now_us.isoformat()
            executed = True

    if executed:
        # Prune records older than 14 days
        cutoff = (now_utc.timestamp() - 14 * 86400)
        to_del = []
        for k, v in completed.items():
            try:
                t = datetime.fromisoformat(v).timestamp()
                if t < cutoff:
                    to_del.append(k)
            except Exception:
                pass
        for k in to_del:
            del completed[k]
        save_daemon_state(state)

    return executed


def run_daemon_loop(poll_interval_sec: int = 20):
    logger.info("Starting Cloud Autonomous Dual-Pod Daemon (24/7/365)...")
    logger.info(f"System Root: {PROJECT_ROOT}")
    logger.info(f"Polling interval: {poll_interval_sec}s")
    state = load_daemon_state()

    while True:
        try:
            now_utc = datetime.now(ZoneInfo("UTC"))
            check_and_trigger(now_utc, state)
        except Exception as e:
            logger.error(f"Unexpected error in daemon loop: {e}", exc_info=True)
        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    run_daemon_loop()
