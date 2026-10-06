import yfinance as yf
import pandas as pd
import numpy as np

print("Loading NSE Midcap 150 Constituents...")
df = pd.read_csv('midcap150.csv')
symbols = [f"{sym}.NS" for sym in df['Symbol'].tolist()]

print(f"Downloading 20 years of data for {len(symbols)} Indian Midcaps... (This will take ~30 seconds)")
data = yf.download(symbols, start="2006-01-01", end="2026-10-06", progress=False, auto_adjust=True, ignore_tz=True)["Close"]

print("Crunching vectorized monthly rebalance...")
# Calculate 50 and 200 SMA
sma50 = data.rolling(window=50).mean()
sma200 = data.rolling(window=200).mean()

# Signal: 1 if 50 > 200, else 0
signals = (sma50 > sma200).astype(int).shift(1)

# Daily returns
returns = data.pct_change()

# Monthly rebalance mask
is_month_end = data.index.is_month_end | (data.index.to_series().dt.month != data.index.to_series().shift(-1).dt.month)

# Create a weight matrix that ONLY updates on month end, otherwise it holds
# Active assets count per day
n_active = signals.sum(axis=1)

# Distribute 100% of capital equally among active assets (0% in cash)
target_weights = signals.div(n_active, axis=0).fillna(0)

# Resample weights to monthly
weights = target_weights.where(is_month_end).ffill()

# Daily portfolio return
portfolio_returns = (weights * returns).sum(axis=1)

# Calculate cumulative equity
equity_curve = (1 + portfolio_returns).cumprod()

print("="*50)
print(f"20-YEAR NSE MIDCAP 150 PORTFOLIO (MONTHLY REBALANCE)")
print(f"Universe: All {len(symbols)} Current NIFTY Midcap Constituents")
print(f"Start Date: {data.index[0].date()}")
print(f"End Date:   {data.index[-1].date()}")
print(f"Total Return: {(equity_curve.iloc[-1] - 1) * 100:.2f}%")
print(f"Max Drawdown: {((equity_curve / equity_curve.cummax()) - 1).min() * 100:.2f}%")
print(f"Final Equity (on $100k): ${100000 * equity_curve.iloc[-1]:,.2f}")
print("="*50)
