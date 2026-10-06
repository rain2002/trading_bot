import yfinance as yf
import pandas as pd
import numpy as np

symbols = ["SPY", "QQQ", "MSFT", "AAPL"]
data = yf.download(symbols, start="2000-01-01", end="2026-10-06", progress=False, auto_adjust=True)["Close"]

# Calculate 50 and 200 SMA
sma50 = data.rolling(window=50).mean()
sma200 = data.rolling(window=200).mean()

# Signal: 1 if 50 > 200, else 0
signals = (sma50 > sma200).astype(int).shift(1)

# Daily returns
returns = data.pct_change()

# We only want to rebalance on the LAST trading day of each month
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

spy_bh = (1 + returns["SPY"]).cumprod().iloc[-1] - 1
qqq_bh = (1 + returns["QQQ"]).cumprod().iloc[-1] - 1

print("="*50)
print(f"26-YEAR USA PORTFOLIO (TREND FOLLOWING - MONTHLY REBALANCE)")
print(f"Symbols: {symbols}")
print(f"Start Date: {data.index[0].date()}")
print(f"End Date:   {data.index[-1].date()}")
print(f"Total Return: {(equity_curve.iloc[-1] - 1) * 100:.2f}%")
print(f"Max Drawdown: {((equity_curve / equity_curve.cummax()) - 1).min() * 100:.2f}%")
print(f"Final Equity (on $100k): ${100000 * equity_curve.iloc[-1]:,.2f}")
print("-"*50)
print(f"BENCHMARK: SPY Buy & Hold: {spy_bh * 100:.2f}%")
print(f"BENCHMARK: QQQ Buy & Hold: {qqq_bh * 100:.2f}%")
print("="*50)
