import yfinance as yf
import pandas as pd
from datetime import datetime
from trading_system.app.research.llm_brain import InvestorSkillsHeuristics

symbols = ["SPY", "QQQ"]
print("Downloading Data for LLM Brain Analysis...")
data = yf.download(symbols, start="2005-01-01", end="2026-10-06", progress=False, auto_adjust=True, ignore_tz=True)["Close"]

# Run Vectorized Logic to simulate LLM Brain returns
sma20 = data.rolling(window=20).mean()
sma50 = data.rolling(window=50).mean()

# LLM Logic: Bullish if Price > SMA20 > SMA50
signals = ((data > sma20) & (sma20 > sma50)).astype(int).shift(1)

returns = data.pct_change()
is_month_end = data.index.is_month_end | (data.index.to_series().dt.month != data.index.to_series().shift(-1).dt.month)

n_active = signals.sum(axis=1)
target_weights = signals.div(n_active, axis=0).fillna(0)
weights = target_weights.where(is_month_end).ffill()

portfolio_returns = (weights * returns).sum(axis=1)
equity_curve = (1 + portfolio_returns).cumprod()

print("="*50)
print(f"LLM BRAIN META-STRATEGY (USA MEGA CAP)")
print(f"Total Return: {(equity_curve.iloc[-1] - 1) * 100:.2f}%")
print(f"Max Drawdown: {((equity_curve / equity_curve.cummax()) - 1).min() * 100:.2f}%")
print("="*50)

# Let's peek into the LLM Brain's rationales on specific historical days
dates_to_inspect = ["2007-10-09", "2008-09-15", "2009-04-01", "2020-02-19", "2020-03-23", "2021-12-01"]
print("\n--- LLM BRAIN THINKING LOG ---")

for date_str in dates_to_inspect:
    date_obj = pd.to_datetime(date_str)
    # Get closest available date
    available_dates = data.index[data.index <= date_obj]
    if len(available_dates) == 0: continue
    closest_date = available_dates[-1]
    
    print(f"\n[Date: {closest_date.date()}]")
    for sym in symbols:
        df = pd.DataFrame({'close': data[sym].loc[:closest_date]})
        judgment = InvestorSkillsHeuristics.apply_judgment(sym, df)
        print(f" > {sym}: {judgment['rationale']} (Confidence: {judgment['confidence']}, Weight: {judgment['target_weight']})")

