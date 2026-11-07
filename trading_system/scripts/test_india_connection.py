"""
Diagnostic Tool: Test Indian Market Connection & Live Data Feeds
================================================================
Checks:
  1. Indian Broker configuration (Groww / Dhan live vs paper fallback mode)
  2. NSE Benchmark Index (^NSEI) live market connection
  3. NSE Individual Equities live price feed (sample leaders)
  4. Paper State Ledger integrity
"""

import os
import sys
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

print("=" * 70)
print("            INDIAN MARKET INFRASTRUCTURE & CONNECTION TEST            ")
print("=" * 70)

# 1. BROKER CONFIGURATION
print("\n[1/4] Checking Indian Broker Credentials in .env...")
broker_type = os.getenv("INDIA_BROKER_TYPE", "GROWW")
api_key = os.getenv("INDIA_API_KEY") or os.getenv("GROWW_API_KEY", "")
api_secret = os.getenv("INDIA_API_SECRET") or os.getenv("GROWW_API_SECRET", "")
totp = os.getenv("INDIA_TOTP_SECRET") or os.getenv("GROWW_AUTH_TOKEN", "")

has_real_keys = bool(api_key and "placeholder" not in api_key.lower())
print(f"  • Broker Adapter Target: {broker_type}")
if has_real_keys:
    print(f"  • Live Broker Status: [ONLINE] Live API Key detected ({api_key[:4]}***).")
    try:
        from trading_system.app.broker.groww import GrowwBrokerAdapter
        adapter = GrowwBrokerAdapter(api_key=api_key, api_secret=api_secret, totp_secret=totp, is_live=True)
        conn = adapter.is_connected()
        print(f"  • Live Broker Handshake: {'CONNECTED' if conn else 'FAILED'}")
    except Exception as e:
        print(f"  • Live Broker Handshake: Warning - {e}")
else:
    print("  • Mode: [GATE B PAPER TRADING] - Using Institutional Local Ledger Engine.")
    print("    (Live Groww/Dhan CNC order routing will activate if real API keys are entered).")

# 2. NSE BENCHMARK DATA
print("\n[2/4] Testing Live NSE Benchmark Data Feed (^NSEI)...")
import yfinance as yf

try:
    nsei_ticker = yf.Ticker("^NSEI")
    nsei_df = nsei_ticker.history(period="5d")
    if not nsei_df.empty:
        last_nsei = float(nsei_df["Close"].iloc[-1])
        last_dt = str(nsei_df.index[-1].strftime("%Y-%m-%d"))
        print(f"  • [SUCCESS] Nifty 50 (^NSEI) Connected: {last_nsei:,.2f} INR (Close Date: {last_dt})")
    else:
        print("  • [-] Warning: ^NSEI returned empty DataFrame.")
except Exception as e:
    print(f"  • [-] Error fetching ^NSEI: {e}")

# 3. NSE EQUITIES DATA FEED
print("\n[3/4] Testing Live NSE Equities Price Feed...")
test_symbols = ["TRENT.NS", "DIXON.NS", "COFORGE.NS", "RELIANCE.NS", "BHARATFORG.NS"]
try:
    stock_df = yf.download(test_symbols, period="5d", progress=False)
    if not stock_df.empty:
        print(f"  • [SUCCESS] Downloaded recent price history for {len(test_symbols)} sample NSE equities:")
        for sym in test_symbols:
            try:
                if isinstance(stock_df.columns, yf.pandas.MultiIndex):
                    if sym in stock_df.columns.levels[-1]:
                        p = float(stock_df["Close"][sym].dropna().iloc[-1])
                    else:
                        p = float(stock_df.xs(sym, axis=1, level=-1)["Close"].dropna().iloc[-1])
                else:
                    p = float(stock_df["Close"].dropna().iloc[-1])
                print(f"    - {sym:15s}: Rs {p:,.2f}")
            except Exception:
                try:
                    p = float(stock_df["Close"][sym].dropna().iloc[-1])
                    print(f"    - {sym:15s}: Rs {p:,.2f}")
                except Exception as ex:
                    print(f"    - {sym:15s}: Rs Fetch Error ({ex})")
except Exception as e:
    print(f"  • [-] Equities fetch warning: {e}")

# 4. PAPER LEDGER INTEGRITY
print("\n[4/4] Verifying Indian Paper Ledger & State File...")
import json
state_file = os.path.join(PROJECT_ROOT, "trading_system", "data", "paper_state_india.json")
if os.path.exists(state_file):
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        cash = state.get("cash", 0)
        pos_cnt = len(state.get("positions", {}))
        hwm = state.get("hwm_true", 0)
        defense = state.get("in_tier4_defense", False)
        print(f"  • [SUCCESS] State file verified: {state_file}")
        print(f"    - Starting Capital : Rs {state.get('initial_capital', 1000000.0):,.2f}")
        print(f"    - Current Cash     : Rs {cash:,.2f}")
        print(f"    - Active Positions : {pos_cnt}")
        print(f"    - High-Water Mark  : Rs {hwm:,.2f}")
        print(f"    - Bear Defense     : {'ACTIVE' if defense else 'NORMAL'}")
    except Exception as e:
        print(f"  • [-] Error reading state: {e}")
else:
    print("  • State file will be initialized on first run.")

print("\n" + "=" * 70)
print("             INDIAN INFRASTRUCTURE CONNECTION TEST COMPLETE          ")
print("=" * 70)
