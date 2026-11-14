# Protocol Amendment V1.2: Phase 1 ETF Strategy Trial Family Declaration & Deflated Sharpe Formulation

**Document ID**: `AMENDMENT-ETF-GOLD-BONDS-V1-2-20261114`  
**Classification**: Formal Protocol Amendment & Mathematical Precision Lock  
**Base Protocol**: [`ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.md`](ETF_GOLD_BONDS_ROTATION_PROTOCOL_V1.md) (`PROTOCOL-ETF-GOLD-BONDS-ROTATION-V1-20261112`)  
**Prior Amendment**: [`ETF_GOLD_BONDS_AMENDMENT_V1_1.md`](ETF_GOLD_BONDS_AMENDMENT_V1_1.md) (`AMENDMENT-ETF-GOLD-BONDS-V1-1-20261114`)  
**Date**: 2026-11-14  
**Target Capital**: ₹80,000 (Initial Gate B allocation)  
**Governance Authority**: Multi-Bot Trading System Master Plan (Phase 1: ETF & Gold Bot)  

---

## 1. Context & Purpose of Amendment V1.2

This amendment resolves two critical mathematical and methodological specifications in the Gate A evaluation of the Phase 1 ETF & Gold Bot:

1. **Deflated Sharpe Ratio (DSR) Unit Scaling**:
   Under the Bailey & López de Prado (2014) Deflated Sharpe Ratio formulation, the standard error of the estimated Sharpe ratio and its expected maximum under selection bias must share consistent time units. In prior test runners, standard error was computed from daily observations without annualizing to match the annualized Sharpe ratio and historical variance, creating an unscaled standard error distorted by $\sqrt{252} \approx 15.87$. This amendment codifies the mathematically exact unit-consistent DSR formulation.

2. **Phase 1 Strategy Trial Family Declaration ($N = 2$)**:
   In accordance with institutional multiple-testing methodology and identical to the trial family pre-registration established in Phase 2 Test T1, the trial family for Phase 1 ETF allocation is formally defined as the set of strategies tested under the Phase 1 Mandate:
   - **Candidate 1**: Dynamic 200-SMA Trend Rotation with Drawdown Throttle.
   - **Champion**: Static 5-Asset Mix with Sovereign Gilts (Rebalanced Annually).
   
   The trial family size is pre-registered up front as $N = 2$. Unrelated historical trials exploring individual equities, statistical arbitrage pairs, or machine learning alpha factors belong to distinct strategy pods and are excluded from the Phase 1 ETF selection bias denominator. Any further variation tested in Phase 1 raises $N$.

---

## 2. Mathematical Specification of Deflated Sharpe Ratio

Per Bailey & López de Prado (2014, *The Journal of Portfolio Management*):

### Expected Maximum Sharpe Ratio:
$$E[\max_N \{SR\}] \approx \sqrt{V[SR]} \left( (1 - \gamma) Z^{-1}\left(1 - \frac{1}{N}\right) + \gamma Z^{-1}\left(1 - \frac{1}{N e}\right) \right)$$
where $\gamma \approx 0.5772156649$ is the Euler-Mascheroni constant, $V[SR]$ is the variance of Sharpe ratios across the trial family, and $Z^{-1}$ is the standard normal quantile function.

### Unit-Consistent Standard Error:
For an annualized Sharpe ratio $SR_{\text{ann}}$ evaluated over $T$ daily sessions:
$$SE(SR_{\text{ann}}) = \sqrt{ \frac{252}{T - 1} \left( 1 - \gamma_3 \left(\frac{SR_{\text{ann}}}{\sqrt{252}}\right) + \frac{\gamma_4 - 1}{4} \left(\frac{SR_{\text{ann}}}{\sqrt{252}}\right)^2 \right) }$$
where $\gamma_3$ and $\gamma_4$ are the sample skewness and kurtosis of daily returns.

### Deflated Sharpe Ratio:
$$Z = \frac{SR_{\text{ann}} - E[\max_N \{SR\}]}{SE(SR_{\text{ann}})}, \quad DSR = \Phi(Z)$$

---

## 3. Pre-Registered Gate A Evaluation Hurdle

The Gate A hurdle for Deflated Sharpe Ratio remains strictly:
$$DSR \ge 0.95 \quad (95.0\% \text{ statistical confidence under } N = 2 \text{ declared trial family})$$

---

## 4. Execution Governance

- This amendment is committed alone with its SHA-256 hash prior to execution of any code.
- Gate A clearance of the Phase 1 Champion is verified against this formulation.
- Sign-off: @Raja Nithin
