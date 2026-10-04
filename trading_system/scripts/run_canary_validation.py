import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from trading_system.app.config.settings import settings
from trading_system.app.reporting.canary_validation import CanaryValidationEngine
import yfinance as yf

def run_canary_check():
    print("="*60)
    print(">>> PHASE 16: CANARY/LIVE EXECUTION VALIDATION REPORT <<<")
    print("="*60)
    
    API_KEY = settings.PAPER_API_KEY
    API_SECRET = settings.PAPER_API_SECRET
    
    if not API_KEY or not API_SECRET:
        print("ERROR: Alpaca API credentials not found in environment.")
        return
        
    validator = CanaryValidationEngine(api_key=API_KEY, api_secret=API_SECRET)
    
    # Check the last 24 hours of executions (since we just ran the live bot)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=1)
    
    print(f"\n[1/3] Querying Alpaca Broker for real executions since {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC...")
    live_df = validator.fetch_live_executions(start_time, end_time)
    
    if live_df.empty:
        print("\n[RESULT] No executed orders found in the specified window.")
        return
        
    print(f"\n[2/3] Recovering {len(live_df)} executions. Fetching expected execution prices...")
    
    # To determine the "Expected Price", we look at the previous close or open of the day
    # Since the live bot uses the most recent close as its 'price_hint', we fetch that.
    symbols = live_df['symbol'].unique().tolist()
    expected_prices = {}
    
    try:
        # Fetching today's latest price to approximate what the bot saw during execution
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            hist = tickers.tickers[sym].history(period="5d")
            if not hist.empty:
                expected_prices[sym] = hist['Close'].iloc[-1]
    except Exception as e:
        print(f"Failed to fetch expected prices from yfinance: {e}")
        
    print("\n[3/3] Calculating Divergence (Latency, Slippage, Partial Fills)...")
    report = validator.generate_divergence_report(live_df, expected_prices)
    
    print("\n" + "-"*40)
    print("CANARY EXECUTION REPORT:")
    print("-"*40)
    print(f"Total Orders Analyzed    : {report.get('total_orders')}")
    print(f"Fully Filled Orders      : {report.get('fully_filled')} ({report.get('fully_filled')/report.get('total_orders')*100:.1f}%)")
    print(f"Partially Filled Orders  : {report.get('partially_filled')}")
    print(f"Avg Execution Latency    : {report.get('average_latency_seconds')} seconds")
    print(f"Avg Slippage (bps)       : {report.get('average_slippage_bps')} bps")
    print("\nAsset-Level Slippage (Negative = Worse than expected):")
    for sym, slip in report.get("slippage_by_symbol", {}).items():
        print(f"  {sym.ljust(6)} : {slip} bps")
        
    print("\n" + "="*60)

if __name__ == "__main__":
    run_canary_check()
