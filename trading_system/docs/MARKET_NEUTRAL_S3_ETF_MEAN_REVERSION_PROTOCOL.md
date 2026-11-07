# Pre-Registered Research Protocol: S3 One-Day ETF Mean Reversion Test
**Document ID**: `PROTOCOL-MKT-NEUTRAL-S3-ETF-MEAN-REV-20261107`  
**Classification**: Institutional Pre-Registration Document (Fiduciary Stage 1)  
**Status**: PRE-REGISTERED (LOCKED PRIOR TO SIMULATION EXECUTION)  
**Creation Date**: 2026-11-07  
**In-Sample Window**: 2007-09-24 to 2024-12-31 (17.27 Years | 4,235 Trading Days)  
**Out-of-Sample Holdout**: 2025-01-01 to 2025-12-31 (Strictly Sealed & Blinded)  
**Governance Authority**: FINAL_MASTER_HEDGE_FUND_ROADMAP.md (Section 3, Chapter 2)

---

## 1. Research Hypothesis & Empirical Basis

Short-term mean reversion at the daily frequency is one of the most robust documented anomalies in high-liquidity index instruments (Lehmann, 1990; Lo and MacKinlay, 1990; Bouchaud et al., 2004). Sudden liquidity shocks, institutional rebalancing flows, and retail margin-call liquidations cause temporary price dislocations that systematically rebound over 1 to 3 trading sessions.

However, in Indian equity markets, **short-term trading is subject to severe statutory friction**:
- Securities Transaction Tax (STT) of 0.10% on delivery sells
- Depository Participant (DP) flat exit fees of ₹14.75 per sell
- Stamp duty (0.015%), exchange turnover fees, and SEBI charges
- Brokerage and ETF bid-ask spread friction (7.5 to 15 bps)

**Hypothesis**: By restricting mean-reversion trades strictly to the **Top 4 Most Liquid Indian ETFs** and utilizing **1-day extreme dislocation entries hedged against market beta**, we can empirically determine whether short-term mean-reversion produces genuine net alpha after overcoming round-trip transaction friction and statutory Indian capital gains tax.

---

## 2. Point-in-Time Universe & Instruments

The strategy operates strictly on the liquid ETF complex in India:

| Ticker | Underlying Benchmark | Asset Class | Historic Inception | Expected Bid-Ask Spread |
| :--- | :--- | :--- | :--- | :--- |
| **NIFTYBEES** | Nifty 50 Index | Large-Cap Equity | 2002-01-08 | 5.0 bps |
| **BANKBEES** | Nifty Bank Index | Banking & Financials | 2004-05-27 | 7.5 bps |
| **JUNIORBEES** | Nifty Next 50 Index | Large-to-Mid Equities | 2003-02-21 | 10.0 bps |
| **GOLDBEES** | Domestic Physical Gold | Precious Metals | 2007-03-08 | 7.5 bps |

**Back-Fill Invariant**: Inception dates are strictly adhered to. If an instrument has not yet commenced trading on date $t$, its portfolio weight allocation is strictly diverted to cash buffer.

---

## 3. Signal Mechanics & Execution Rules

1. **Short-Term Dislocation Indicator**:
   - **Connors 2-Period RSI (RSI(2))**: Computed on daily close prices:
     $$\text{RSI}(2) = 100 - \frac{100}{1 + \frac{\text{EMA}_2(\text{Gains})}{\text{EMA}_2(\text{Losses})}}$$
   - **Normalized Return Dislocation ($z$-score)**:
     $$z_t = \frac{r_{1d, t} - \mu_{20}(r_{1d})}{\sigma_{20}(r_{1d})}$$
     where $\sigma_{20}$ is the Barroso & Santa-Clara (2015) 20-day realized volatility.

2. **Entry Condition (Extreme Oversold Dislocation)**:
   - An ETF qualifies for entry when:
     $$\text{RSI}(2) \le 10.0 \quad \text{AND} \quad z_t \le -2.00$$
   - **Trend Filter Condition**: The ETF's underlying 200-day simple moving average must be flat or rising ($\text{Price} \ge 0.95 \times \text{SMA}_{200}$), preventing dip-buying into structural bankruptcy collapses.
   - Entry occurs at **Market Close of day $t$** (or next morning Open $t+1$).

3. **Market-Neutral Hedging & Pair Dislocation**:
   - For equity ETFs (BANKBEES, JUNIORBEES), the long position is simultaneously hedged against a short position in NIFTYBEES (or Nifty 50 index future) scaled to equal beta:
     $$w_{\text{hedge}} = -\beta_{\text{ETF}} \times w_{\text{long}}$$
   - For NIFTYBEES vs GOLDBEES, statistical spread divergence is evaluated using rolling cointegration z-scores ($|z_{\text{spread}}| > 2.0$).

4. **Exit Rules (Strict 1-to-3 Day Horizon)**:
   - **Time-Stop**: Position is closed unconditionally after **1 trading day** (Close $t+1$), or maximum **3 trading days** (Close $t+3$).
   - **Profit-Target Rebound**: Position is exited immediately when $\text{RSI}(2) \ge 65.0$.
   - **Stop-Loss Mandate**: Hard catastrophic stop at **-3.5%** per trade.

---

## 4. Statutory Friction & Cost Accounting

Because 1-day mean-reversion generates substantial trade volume, transaction costs are simulated with high rigor:
1. **Slippage**: 7.5 bps per leg (Normal) | 12.5 bps per leg (Stressed Gate A).
2. **STT**: 0.10% on deliveries (sell leg).
3. **DP Exit Fee**: ₹14.75 flat per delivery sale.
4. **Exchange, SEBI & Stamp Charges**: 0.00297% NSE, 0.0001% SEBI, 0.015% stamp duty.
5. **Taxation**: All realized gains are classified as Short-Term Capital Gains (STCG) taxed at 20.8% (or 31.2% slab rate sensitivity).

---

## 5. Mandatory Gate A Clearance Hurdles

| Metric | Hurdle Threshold | Rationale |
| :--- | :--- | :--- |
| **Post-Tax, Post-Friction Net CAGR** | $\ge 10.00\%$ | Strategy must prove positive alpha beyond friction drag |
| **Maximum Drawdown (Peak-to-Trough)** | $\le -12.00\%$ | High-turnover mean reversion must possess tight drawdown control |
| **Sharpe Ratio (Annualized)** | $\ge 1.10$ | High-frequency edge must show superior risk-adjusted return |
| **Win Rate** | $\ge 58.0\%$ | Mean reversion edge requires a clear statistical win frequency |
| **Profit Factor** | $\ge 1.40$ | Gross profits must comfortably exceed gross losses |
| **Total Closed Trades** | $\ge 150$ trades | Robust statistical sample size across the 17.27-year window |
| **2025 Calendar Holdout** | STRICTLY SEALED | Out-of-sample holdout must remain 100% untouched |

---

## 6. Pre-Registration Integrity Hash
This protocol is committed **alone** to git prior to writing backtest code or running historical simulations.
