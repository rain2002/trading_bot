import yfinance as yf
import pandas as pd
import numpy as np

# A classic Global Tactical Asset Allocation ETF Basket
# By trading ETFs directly, we COMPLETELY eliminate survivorship bias!
symbols = [
    "SPY",  # US Large Caps
    "IWM",  # US Small Caps 
    "EFA",  # Developed International Markets
    "EEM",  # Emerging Markets
    "TLT",  # US Long-Term Treasury Bonds
    "GLD",  # Gold
    "VNQ"   # US Real Estate (REITs)
]

print(f"Downloading data for Global ETF Basket: {symbols}")
# We use max data available. Most of these launched around 2003-2004.
data = yf.download(symbols, start="2005-01-01", end="2026-10-06", progress=False, auto_adjust=True, ignore_tz=True)["Close"]

# Calculate 50 and 200 SMA
sma50 = data.rolling(window=50).mean()
sma200 = data.rolling(window=200).mean()

# Signal: 1 if 50 > 200 (Uptrend), else 0 (Cash)
signals = (sma50 > sma200).astype(int).shift(1)

# Daily returns
returns = data.pct_change()

# Monthly rebalance mask
is_month_end = data.index.is_month_end | (data.index.to_series().dt.month != data.index.to_series().shift(-1).dt.month)

# Active assets count per day
n_active = signals.sum(axis=1)

# Distribute capital equally among active assets
target_weights = signals.div(n_active, axis=0).fillna(0)

# Resample weights to monthly
weights = target_weights.where(is_month_end).ffill()

# Daily portfolio return
portfolio_returns = (weights * returns).sum(axis=1)

# Calculate cumulative equity
equity_curve = (1 + portfolio_returns).cumprod()

# Benchmark: Equal Weight Buy & Hold of the exact same ETFs
benchmark_weights = pd.DataFrame(1.0 / len(symbols), index=returns.index, columns=returns.columns)
benchmark_monthly_weights = benchmark_weights.where(is_month_end).ffill()
benchmark_returns = (benchmark_monthly_weights * returns).sum(axis=1)
benchmark_curve = (1 + benchmark_returns).cumprod()

print("="*50)
print(f"HONEST ETF PORTFOLIO (ZERO SURVIVORSHIP BIAS)")
print(f"Start Date: {data.index[0].date()}")
print(f"End Date:   {data.index[-1].date()}")
print(f"Total Return: {(equity_curve.iloc[-1] - 1) * 100:.2f}%")
print(f"Max Drawdown: {((equity_curve / equity_curve.cummax()) - 1).min() * 100:.2f}%")
print(f"Final Equity (on $100k): ${100000 * equity_curve.iloc[-1]:,.2f}")
print("-" * 50)
print(f"BENCHMARK: Buy & Hold (Same ETFs): {(benchmark_curve.iloc[-1] - 1) * 100:.2f}%")
print(f"BENCHMARK Max Drawdown: {((benchmark_curve / benchmark_curve.cummax()) - 1).min() * 100:.2f}%")
print("="*50)
