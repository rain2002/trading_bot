"""
NSE Whole-Market Candidate S2 — Zero-Capital Exploratory Forward Shadow Bot
=========================================================================
Strictly non-ETF individual NSE equity momentum strategy based on audited
Phase 5 Candidate S2 (22.34% CAGR, 1.23 Sharpe on V2 full-panel corporate actions):
  - Universe : ind_nifty500list.csv filtered to INE-series EQ stocks (ZERO ETFs)
  - Liquidity: Close >= INR 20, trailing 60D median traded value >= INR 2.0 Cr, >= 252d history
  - Ranking  : 0.60 * Clenow(90d) + 0.40 * Clenow(180d) on stocks > 150-SMA
  - Slots    : Up to 15 core slots (max 8.0% equity per entry)
  - Exits    : 150-SMA trend break, -12% hard stop, tiered profit trails (+25%/15%, +50%/20%, +100%/25%)
  - Macro    : ^NSEI 200-SMA Bear Defense + Barroso & Santa-Clara Vol Radar (target_vol=0.15)
  - Costs    : Dhan INR 15.93 DP sell fee + 27.0 bps buy / 25.5 bps sell + 6.0% cash yield
  - Custody  : Zero real capital. Persists strictly to state-shadow-nse branch.
"""

import os
import sys
import math
import json
import hashlib
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from trading_system.app.data.corporate_actions import is_etf_ticker, is_valid_equity_isin
from trading_system.app.research.momentum_crash import evaluate_dual_pod_regime_and_volatility

DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
NIFTY500_CSV = os.path.join(DATA_DIR, "ind_nifty500list.csv")
STATE_FILE = os.path.join(DATA_DIR, "nse_s2_shadow_state.json")
TRADES_CSV = os.path.join(DATA_DIR, "nse_s2_shadow_trades.csv")
EQUITY_LOG_CSV = os.path.join(DATA_DIR, "nse_s2_shadow_equity_log.csv")

INITIAL_CAPITAL = 80000.0
CORE_SLOTS = 15
MAX_ALLOC_PCT = 0.08
MIN_SHARE_PRICE = 20.0
MIN_MEDIAN_TURNOVER = 20_000_000.0  # INR 2.0 Crore
MIN_HISTORY_DAYS = 252
HARD_STOP_PCT = -0.12
EXIT_SMA_WINDOW = 150
TRAIL_TIERS = [(1.00, -0.25), (0.50, -0.20), (0.25, -0.15)]
BUY_FRICTION_BPS = 27.0
SELL_FRICTION_BPS = 25.5
FLAT_DP_FEE = 15.93
CASH_YIELD_PA = 0.06


def load_nse_s2_equity_universe(csv_path: str = NIFTY500_CSV) -> List[str]:
    """Loads individual NSE equity tickers (.NS) strictly excluding ETFs and funds."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Missing NSE 500 equity list: {csv_path}")
    df = pd.read_csv(csv_path)
    tickers: List[str] = []
    for _, row in df.iterrows():
        sym = str(row.get("Symbol", "")).strip().upper()
        series = str(row.get("Series", "EQ")).strip().upper()
        isin = str(row.get("ISIN Code", "")).strip().upper()
        if not sym or series != "EQ":
            continue
        if isin and not is_valid_equity_isin(isin):
            continue
        if is_etf_ticker(sym):
            continue
        tickers.append(f"{sym}.NS")
    return sorted(list(set(tickers)))


def calc_clenow_score(closes: np.ndarray, window: int) -> float:
    """Clenow annualized exponential regression slope * R^2."""
    if len(closes) < window:
        return 0.0
    seg = np.asarray(closes[-window:], dtype=float)
    if np.any(np.isnan(seg)) or np.any(seg <= 0):
        return 0.0
    log_p = np.log(seg)
    x = np.arange(window, dtype=float)
    slope, intercept = np.polyfit(x, log_p, 1)
    y_pred = slope * x + intercept
    ss_res = float(np.sum((log_p - y_pred) ** 2))
    ss_tot = float(np.sum((log_p - np.mean(log_p)) ** 2))
    r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    ann_slope = math.expm1(float(np.clip(slope * 252.0, -10.0, 10.0)))
    return float(ann_slope * r2)


def fetch_nse_market_data(tickers: List[str], chunk_size: int = 125) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """Batch-downloads NSE equity OHLCV + ^NSEI benchmark, dropping incomplete NaN-close bars."""
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="18mo", progress=False, group_by="ticker", auto_adjust=False)
            for sym in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym in data.columns.levels[0]:
                            df = data[sym].copy()
                        elif sym in data.columns.levels[-1]:
                            df = data.xs(sym, axis=1, level=-1).copy()
                        else:
                            continue
                    else:
                        df = data.copy()
                    df.columns = [str(c).lower() for c in df.columns]
                    if "close" in df.columns:
                        df = df.dropna(subset=["close"])
                    if len(df) >= 60:
                        out[sym] = df
                except Exception:
                    continue
        except Exception as e:
            print(f"[NSE S2 Fetch Warning] Chunk {i}: {e}")

    bench = yf.download("^NSEI", period="18mo", progress=False, auto_adjust=False)
    if isinstance(bench.columns, pd.MultiIndex):
        bench.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in bench.columns]
    else:
        bench.columns = [str(c).lower() for c in bench.columns]
    if "close" in bench.columns:
        bench = bench.dropna(subset=["close"])
    return out, bench


class NSES2ShadowRunner:
    """Zero-capital forward paper runner for NSE Whole-Market Candidate S2."""

    def __init__(
        self,
        state_file: str = STATE_FILE,
        trades_file: str = TRADES_CSV,
        equity_log_file: str = EQUITY_LOG_CSV,
        initial_capital: float = INITIAL_CAPITAL,
    ):
        self.state_file = state_file
        self.trades_file = trades_file
        self.equity_log_file = equity_log_file
        self.initial_capital = initial_capital
        self.session_trades: List[Dict[str, Any]] = []
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "strategy_id": "NSE_S2_EXPLORATORY_SHADOW",
            "currency": "INR",
            "initial_capital": self.initial_capital,
            "cash": self.initial_capital,
            "positions": {},
            "pending_buys": [],
            "pending_sells": [],
            "hwm_true": self.initial_capital,
            "max_drawdown_pct": 0.0,
            "macro_regime": "INITIALIZING",
            "radar_summary": "",
            "last_bar_date": None,
            "days_shadowed": 0,
            "last_updated": None,
        }

    def _save_state(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _log_trade(self, row: Dict[str, Any]):
        self.session_trades.append(dict(row))
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        has_hdr = os.path.exists(self.trades_file) and os.path.getsize(self.trades_file) > 0
        pd.DataFrame([row]).to_csv(self.trades_file, mode="a", index=False, header=not has_hdr)

    def _log_equity(self, session_date: str, equity: float, port_val: float, status: str):
        os.makedirs(os.path.dirname(self.equity_log_file), exist_ok=True)
        hwm = float(self.state.get("hwm_true", self.initial_capital))
        dd_pct = ((equity - hwm) / hwm * 100.0) if hwm > 0 else 0.0
        row = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "session_date": session_date,
            "nav": round(equity, 2),
            "cash": round(float(self.state["cash"]), 2),
            "holdings_val": round(port_val, 2),
            "hwm_true": round(hwm, 2),
            "drawdown_pct": round(dd_pct, 2),
            "open_positions": len(self.state["positions"]),
            "macro_regime": self.state.get("macro_regime", ""),
            "status": status,
        }
        has_hdr = os.path.exists(self.equity_log_file) and os.path.getsize(self.equity_log_file) > 0
        if has_hdr:
            df = pd.read_csv(self.equity_log_file, dtype=str)
            df = df[df["session_date"].astype(str) != str(session_date)]
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(self.equity_log_file, index=False)
        else:
            pd.DataFrame([row]).to_csv(self.equity_log_file, index=False)

    def run_daily_cycle(
        self,
        universe_data: Optional[Dict[str, pd.DataFrame]] = None,
        bench_df: Optional[pd.DataFrame] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if universe_data is None or bench_df is None:
            tickers = load_nse_s2_equity_universe()
            held = list(self.state.get("positions", {}).keys())
            all_syms = sorted(list(set(tickers) | set(held)))
            universe_data, bench_df = fetch_nse_market_data(all_syms)

        if bench_df is None or bench_df.empty:
            return {"status": "FAIL_CLOSED_NO_BENCHMARK"}

        latest_bar_date = str(bench_df.index[-1])[:10]
        if not force and self.state.get("last_bar_date") == latest_bar_date:
            print(f"[NSE S2 IDEMPOTENCY] Session {latest_bar_date} already processed; skipping.")
            return {"status": "ALREADY_PROCESSED", "session_date": latest_bar_date}

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Execute prior session's queued sells & buys at today's official Open (zero lookahead)
        buy_fee = BUY_FRICTION_BPS / 10000.0
        sell_fee = SELL_FRICTION_BPS / 10000.0

        for item in self.state.get("pending_sells", []):
            sym = item["sym"]
            if sym not in self.state["positions"] or sym not in universe_data:
                continue
            df = universe_data[sym]
            open_px = float(df["open"].dropna().iloc[-1]) if "open" in df.columns and not df["open"].dropna().empty else float(df["close"].iloc[-1])
            if math.isnan(open_px) or open_px <= 0:
                continue
            pos = self.state["positions"][sym]
            shs = float(pos["shares"])
            fill_p = open_px * (1.0 - sell_fee)
            proceeds = shs * fill_p - FLAT_DP_FEE
            pnl = proceeds - (shs * float(pos["entry_price"]))
            self.state["cash"] += max(0.0, proceeds)
            self._log_trade({
                "timestamp": now_str, "session_date": latest_bar_date,
                "symbol": sym, "action": "SELL", "shares": shs,
                "fill_price": round(fill_p, 2), "trade_value": round(shs * fill_p, 2),
                "realized_pnl": round(pnl, 2), "reason": item.get("reason", "SIGNAL_EXIT"),
            })
            del self.state["positions"][sym]
        self.state["pending_sells"] = []

        for item in self.state.get("pending_buys", []):
            sym = item["sym"]
            if sym in self.state["positions"] or sym not in universe_data or is_etf_ticker(sym):
                continue
            df = universe_data[sym]
            open_px = float(df["open"].dropna().iloc[-1]) if "open" in df.columns and not df["open"].dropna().empty else float(df["close"].iloc[-1])
            if math.isnan(open_px) or open_px <= MIN_SHARE_PRICE:
                continue
            fill_p = open_px * (1.0 + buy_fee)
            alloc = min(float(item["target_alloc"]), float(self.state["cash"]) * 0.96)
            shs = math.floor(alloc / fill_p)
            cost = shs * fill_p
            if shs > 0 and cost <= self.state["cash"]:
                self.state["cash"] -= cost
                self.state["positions"][sym] = {
                    "shares": shs,
                    "entry_price": round(fill_p, 4),
                    "entry_date": latest_bar_date,
                    "peak_price": round(fill_p, 4),
                    "last_close": round(float(df["close"].iloc[-1]), 4),
                }
                self._log_trade({
                    "timestamp": now_str, "session_date": latest_bar_date,
                    "symbol": sym, "action": "BUY", "shares": shs,
                    "fill_price": round(fill_p, 2), "trade_value": round(cost, 2),
                    "realized_pnl": 0.0, "reason": f"S2_ENTRY Score={item.get('score', 0):.2f}",
                })
        self.state["pending_buys"] = []

        # Credit daily overnight liquid yield on idle cash (6.0% p.a.)
        daily_yield = (1.0 + CASH_YIELD_PA) ** (1.0 / 252.0) - 1.0
        self.state["cash"] = float(self.state["cash"]) * (1.0 + daily_yield)

        # 2. Mark positions to market on today's close
        port_val = 0.0
        for sym, pos in self.state["positions"].items():
            px = float(pos.get("last_close", pos["entry_price"]))
            if sym in universe_data and not universe_data[sym].empty:
                c_val = float(universe_data[sym]["close"].iloc[-1])
                if not math.isnan(c_val) and c_val > 0:
                    px = c_val
            pos["last_close"] = round(px, 4)
            pos["peak_price"] = round(max(float(pos.get("peak_price", px)), px), 4)
            port_val += float(pos["shares"]) * px

        equity = float(self.state["cash"]) + port_val
        self.state["hwm_true"] = round(max(float(self.state.get("hwm_true", self.initial_capital)), equity), 2)
        dd_pct = ((equity - self.state["hwm_true"]) / self.state["hwm_true"] * 100.0) if self.state["hwm_true"] > 0 else 0.0
        self.state["max_drawdown_pct"] = round(min(float(self.state.get("max_drawdown_pct", 0.0)), dd_pct), 2)

        # 3. Evaluate Macro Regime & Scan Today's Closes for Next-Open Queue
        radar = evaluate_dual_pod_regime_and_volatility(
            benchmark_df=bench_df, target_vol=0.15, vol_lookback=20,
            crash_vol_threshold=0.24, bear_sma_lookback=200, caution_scale_threshold=0.75,
        )
        macro_regime = radar["regime"]
        max_exposure = float(radar["max_exposure"])
        self.state["macro_regime"] = macro_regime
        self.state["radar_summary"] = (
            f"{macro_regime} (^NSEI {radar['bench_close']:.0f} vs 200-SMA {radar['bench_sma200']:.0f}, "
            f"20D Vol {radar['bench_vol_20d']*100:.1f}%, MaxExp {max_exposure*100:.0f}%)"
        )

        # Evaluate S2 exits
        next_sells = []
        if macro_regime == "BEAR_DEFENSE":
            for sym in list(self.state["positions"].keys()):
                next_sells.append({"sym": sym, "reason": "BEAR_DEFENSE_EXIT"})
        else:
            for sym, pos in list(self.state["positions"].items()):
                px = float(pos["last_close"])
                entry = float(pos["entry_price"])
                peak = float(pos["peak_price"])
                plpc = (px - entry) / entry if entry > 0 else 0.0
                pullback = (px - peak) / peak if peak > 0 else 0.0

                if plpc <= HARD_STOP_PCT:
                    next_sells.append({"sym": sym, "reason": f"HARD_STOP ({plpc*100:+.1f}%)"})
                    continue
                trailed = False
                for min_g, tr_stop in TRAIL_TIERS:
                    if plpc >= min_g and pullback <= tr_stop:
                        next_sells.append({"sym": sym, "reason": f"TRAIL_TIER (+{min_g*100:.0f}%/{tr_stop*100:.0f}%)"})
                        trailed = True
                        break
                if trailed:
                    continue
                if sym in universe_data and len(universe_data[sym]) >= EXIT_SMA_WINDOW:
                    sma150 = float(universe_data[sym]["close"].rolling(EXIT_SMA_WINDOW, min_periods=112).mean().iloc[-1])
                    if px < sma150:
                        next_sells.append({"sym": sym, "reason": f"TREND_SMA150_BREAK ({plpc*100:+.1f}%)"})

        self.state["pending_sells"] = next_sells
        held_after_exits = len(self.state["positions"]) - len(next_sells)
        open_slots = max(0, CORE_SLOTS - held_after_exits)

        next_buys = []
        if macro_regime != "BEAR_DEFENSE" and open_slots > 0 and self.state["cash"] > 500.0:
            cands = []
            for sym, df in universe_data.items():
                if is_etf_ticker(sym) or sym in self.state["positions"] or any(s["sym"] == sym for s in next_sells):
                    continue
                if len(df) < MIN_HISTORY_DAYS:
                    continue
                c_arr = df["close"].values
                cur_p = float(c_arr[-1])
                if math.isnan(cur_p) or cur_p < MIN_SHARE_PRICE:
                    continue
                if "volume" in df.columns:
                    med_val = float((df["close"] * df["volume"]).rolling(60, min_periods=20).median().iloc[-1])
                    if math.isnan(med_val) or med_val < MIN_MEDIAN_TURNOVER:
                        continue
                sma150 = float(pd.Series(c_arr).rolling(EXIT_SMA_WINDOW, min_periods=112).mean().iloc[-1])
                if cur_p <= sma150:
                    continue
                score = 0.60 * calc_clenow_score(c_arr, 90) + 0.40 * calc_clenow_score(c_arr, 180)
                if score > 0.10:
                    cands.append({"sym": sym, "score": score})

            cands.sort(key=lambda x: x["score"], reverse=True)
            avail = float(self.state["cash"]) * 0.96
            target_per_slot = min(equity * MAX_ALLOC_PCT, equity / CORE_SLOTS) * max_exposure
            for c in cands[:open_slots]:
                if avail < 500.0 or target_per_slot < 500.0:
                    break
                alloc = min(target_per_slot, avail)
                next_buys.append({"sym": c["sym"], "target_alloc": round(alloc, 2), "score": round(c["score"], 4)})
                avail -= alloc
        self.state["pending_buys"] = next_buys

        self.state["last_bar_date"] = latest_bar_date
        self.state["days_shadowed"] = int(self.state.get("days_shadowed", 0)) + 1
        self._save_state()

        status = "EXECUTED_AND_SCANNED" if self.session_trades else "SCANNED_HOLD"
        self._log_equity(latest_bar_date, equity, port_val, status)
        self._send_discord(latest_bar_date, equity, port_val, status)
        return {"status": status, "session_date": latest_bar_date, "nav": round(equity, 2), "trades": len(self.session_trades)}

    def _send_discord(self, session_date: str, equity: float, port_val: float, status: str):
        if os.environ.get("ENABLE_NOTIFICATIONS", "0") != "1":
            return
        try:
            from trading_system.app.notifications.notifier import QuantNotifier
            notifier = QuantNotifier()
            if not notifier.discord_url:
                return
            pnl = equity - self.initial_capital
            pnl_pct = (pnl / self.initial_capital * 100.0) if self.initial_capital > 0 else 0.0
            if self.session_trades:
                tr_lines = [
                    f"• `{t['action']}` **{t['shares']:g} {t['symbol']}** @ ₹{t['fill_price']:,.2f}"
                    + (f" (PnL: ₹{t['realized_pnl']:+,.2f})" if t["action"] == "SELL" else "")
                    for t in self.session_trades[:12]
                ]
            else:
                tr_lines = ["• None today"]

            q_sells = [f"`SELL` {s['sym']}" for s in self.state.get("pending_sells", [])]
            q_buys = [f"`BUY` {b['sym']} (₹{b['target_alloc']:,.0f})" for b in self.state.get("pending_buys", [])]
            q_all = q_sells + q_buys
            q_txt = ", ".join(q_all[:10]) if q_all else ("None (100% Cash Defense)" if self.state.get("macro_regime") == "BEAR_DEFENSE" else "None queued")

            hold_lines = [
                f"• **{sym}**: {p['shares']:g} shs @ ₹{p['last_close']:,.2f}"
                for sym, p in sorted(self.state["positions"].items())
            ]
            msg = (
                f"**Status:** `{status}` | **Session:** `{session_date}` (Day {self.state['days_shadowed']})\n"
                f"🛡️ **Macro:** `{self.state.get('radar_summary', 'N/A')}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Shadow Equity:** ₹{equity:,.2f} ({pnl_pct:+.2f}% / ₹{pnl:+,.2f})\n"
                f"💵 **Cash:** ₹{self.state['cash']:,.2f} | **Positions:** {len(self.state['positions'])}/15 | **Max DD:** {self.state['max_drawdown_pct']:.2f}%\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 **Trades Executed ({len(self.session_trades)}):**\n" + "\n".join(tr_lines) + "\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ **Queued Next Open:** {q_txt}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 **Active Holdings:**\n" + ("\n".join(hold_lines[:15]) if hold_lines else "• None (Cash)")
            )
            notifier.send_discord_alert(
                title=f"🇮🇳 NSE Whole-Market S2 Shadow (Non-ETF) — {session_date}",
                message=msg[:3900],
                color=0x00D084 if self.state.get("macro_regime") != "BEAR_DEFENSE" else 0xFFB000,
            )
        except Exception as e:
            print(f"[NSE S2 Discord Warning] {e}")


def main():
    parser = argparse.ArgumentParser(description="NSE Whole-Market Candidate S2 Forward Shadow")
    parser.add_argument("--force", action="store_true", help="Force re-run on same session bar")
    args = parser.parse_args()
    runner = NSES2ShadowRunner()
    res = runner.run_daily_cycle(force=args.force)
    print(f"[NSE S2 SHADOW] Result: {res}")


if __name__ == "__main__":
    main()
