# PROTOCOL AMENDMENT: PRE-REGISTERED DUAL-POD VOLATILITY TARGETING
**Document ID: AMEND_VOL_TARGET_2026_11_07 • Effective Date: 2026-11-07**
**Classification: Institutional Quantitative Research Amendment**

---

## 1. Context & Purpose of Amendment
On 2026-11-07, the exploratory shadow paper trading engine (`run_dual_pod_paper.py`) introduced dynamic inverse volatility scaling and a panic-crash regime filter to defend against momentum crashes. 

To maintain fiduciary provenance, eliminate code divergence, and avoid forward record contamination:
1. **Rule Change Date**: Formally recorded as **2026-11-07**.
2. **Shared Code Path**: Both the backtest engine (`backtest_growth_stock_momentum.py`) and forward execution runner (`run_dual_pod_paper.py`) MUST consume the identical canonical function:
   `trading_system.app.research.momentum_crash.evaluate_dual_pod_regime_and_volatility`
3. **Parameter Invariance**: Target volatility $\sigma_{\text{target}}$ is set to **15.0%** across both India and US desks, justified by matching the historical unconditional annualized volatility of Nifty 50 and S&P 500 benchmarks.
4. **Execution Mechanics**: 
   - Position slot count is fixed at 10 (`MAX_CORE_POSITIONS = 10`).
   - Sizing per candidate is scaled to $(10\% \times w_t)$ (no double-scaling).
   - Holdings exceeding target weight during elevated volatility are dynamically trimmed via `VOL_TARGET_TRIM`.
   - Structural trend breaks (< 200-SMA) or Daniel & Moskowitz panic crash states trigger full capital preservation into safe cash yield (`BEAR_DEFENSE`, $w_t = 0.0$).

---

## 2. Canonical Mathematical Specifications

### A. Barroso & Santa-Clara (2015) Volatility Weight
$$\hat{\sigma}_{20\text{D}, t} = \sqrt{252 \times \frac{1}{19} \sum_{k=0}^{19} (r_{t-k} - \bar{r})^2}$$
$$w_t = \min\left(1.0, \frac{0.15}{\max(\hat{\sigma}_{20\text{D}, t}, 0.08)}\right)$$

### B. Daniel & Moskowitz (2016) Panic Crash Sentinel
$$\text{Panic Condition: } R_{6\text{M}, t} < 0.0 \quad \text{and} \quad \hat{\sigma}_{20\text{D}, t} \ge 0.24$$

### C. Structural Trend Sentinel
$$\text{Trend Condition: } P_{\text{bench}, t} < \text{SMA}_{200}(P_{\text{bench}})_t$$

### D. Regime Determination
$$\text{Regime} = \begin{cases} 
\text{BEAR\_DEFENSE } (w_t = 0.0), & \text{if Panic Condition or Trend Condition is True} \\
\text{VOLATILITY\_CAUTION } (w_t = \text{round}(w_t, 2)), & \text{if } w_t < 0.75 \\
\text{BULL\_TRENDING } (w_t = 1.0), & \text{otherwise}
\end{cases}$$

---

## 3. Pre-Registration Invariant Declaration
- The amendment is committed prior to publishing revised backtest results.
- Unsealed 2025 calendar year holdout remains strictly burned and excluded.
- Results are reported under stressed costs (7.5 bps slippage, DP charges, statutory turnover, STT 10 bps both sides) and post-tax accounting.
