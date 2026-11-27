# Pre-Registered Protocol: NSE S2 Walk-Forward Validation (V1.0)

**Document ID**: `PROTOCOL-NSE-S2-WALK-FORWARD-V1-20261126`  
**Author**: @Raja Nithin  
**Date**: 2026-11-26  
**Status**: SEALED PRE-EXECUTION  
**Panel Version**: `NSE_PANEL_V2`  
**Panel SHA-256**: `d2806b81342339edcd6debf60a8dfcac7042ab7b9f630db1795b925cb68a2156`  
**Corporate Actions Version**: `nse_corporate_actions_v2.csv` (511 events)  
**Corporate Actions SHA-256**: `a04cd4ac4e64b1813e99855fbd47fa73a1a5c22f909a112ab702e28bc123058d`  
**Cumulative Trial Count**: $N = 88$ (prior $N = 86$, plus 1 walk-forward procedure candidate and 1 fixed S2 baseline)

---

## 1. Purpose & Non-Negotiable Governance Rules

This protocol tests a **procedure**, not a single set of parameters: *"re-optimize each year on a fixed 3×3×3 grid using plateau-averaged Sharpe, then trade the next calendar year blind."*

1. **Pre-Registration**: Committed alone with its SHA-256 seal before any walk-forward code is written or executed.
2. **No Post-Hoc Edits**: Any change to the procedure, grid, embargo, cost schedule, or pass/fail rules after seeing a result is a new trial and requires a new protocol (`V2`), never an edit.
3. **Holdout Protection**: The `2023-01-01` to `2024-07-05` holdout remains strictly sealed. It is opened **at most once** only if all 13 checks pass (or if only H4 DSR fails, per the shadow decision rule).

---

## 2. Walk-Forward Design

| Item | Pre-Registered Setting |
|---|---|
| **In-sample span** | `2007-09-17` to `2022-12-31` (`2023-01-01` to `2024-07-05` holdout stays sealed) |
| **Folds** | 10 rolling folds: train on 5 years, test on the next 1 calendar year, slide forward 1 year (`2013` through `2022` test years) |
| **Embargo (Gap)** | Between the end of each training window and the start of the test year (`Jan 1`), an embargo equal to S2's longest completed holding period (in trading days) observed in that training fold (so no trade straddles the train/test boundary) |
| **Knobs (3×3×3 = 27)** | 1. `lookback_90` ∈ `[72, 90, 108]` (`lookback_180 = 2 * lookback_90`, centered at `90` ±20%)<br>2. `exit_sma_window` ∈ `[120, 150, 180]` (centered at `150` ±20%)<br>3. `trail_scale` ∈ `[0.8, 1.0, 1.2]` scaling `(trail_t1_stop, trail_t2_stop, trail_t3_stop)` = `(0.15, 0.20, 0.25)` ±20% |
| **Selection Objective** | Plateau Sharpe: for each grid point $g$, average the training Sharpe across $g$ and all immediate grid neighbours (Manhattan distance $\le 1$ on the 3×3×3 grid). Pick the grid point with the highest plateau-averaged Sharpe. |
| **Cost Schedule** | V1.1 schedule in every fold: Buy `27.0 bps`, Sell `25.5 bps`, Flat DP `₹15.93`. Stress test (H9): `2×` costs (`54.0 bps` buy, `51.0 bps` sell, `₹31.86` DP). |
| **Baselines (2013–2022)** | (a) Fixed S2 (`90 / 150 / 1.0`) over 2013–2022; (b) Control A: 1,000 random-selection runs with the same overlay; (c) Control B: equal-weight liquid top 100 on `adj_close` (V2 CA); (d) Nifty 50 + `1.35% p.a.` dividend yield series |
| **Required Outputs** | One stitched out-of-sample equity curve (`2013–2022`), a per-fold table of chosen settings, in-sample/OOS Sharpe, and walk-forward efficiency (`OOS Sharpe / IS Sharpe`), 13 pass/fail checks, and `trial_log.csv` rows with `N=88`. |

---

## 3. Pass and Fail Rules (13 Checks)

All thresholds are fixed prior to execution over the stitched 10-year out-of-sample curve (`2013-01-01` to `2022-12-31`):

| Check | Rule |
|---|---|
| **H1 Return** | Stitched CAGR $\ge$ Benchmark TRI CAGR $+ 4.0$ percentage points over 2013–2022 |
| **H2 Sharpe** | Stitched annualized Sharpe $\ge 0.80$ |
| **H3 Drawdown** | Stitched Max Drawdown no worse than $-35.0\%$ |
| **H4 DSR** | Deflated Sharpe Ratio $\ge 0.95$ with $N = 88$ |
| **H5 Control A** | Stitched Sharpe $> 95\text{th}$ percentile of 1,000 random-selection runs |
| **H6 Control B** | Beats equal-weight liquid top 100 (`adj_close` V2) in both CAGR and Sharpe |
| **H7 Stability** | Positive excess return in at least 3 of 4 equal sub-periods of 2013–2022 |
| **H8 Plateau** | Passes at $\pm 20\%$ on every knob (Sharpe $\ge 0.70$) |
| **H9 Cost stress** | $2\times$ costs still beats benchmark by $\ge 2.0$ percentage points (and Sharpe $\ge 0.70$) |
| **W1 Efficiency** | Out-of-sample Sharpe $\ge 0.50 \times$ in-sample Sharpe in at least 7 of 10 folds |
| **W2 Beats fixed** | Walk-forward stitched Sharpe $\ge$ fixed S2 Sharpe over 2013–2022 |
| **W3 Top trades** | Still clears H1 with the 5 best out-of-sample trades removed |
| **W4 Settings stability** | Each knob moves by more than one grid step in fewer than 3 of 10 folds |

---

## 4. Decision Matrix

- **All 13 pass**: Open the `2023-01-01` to `2024-07-05` holdout **once**. If it holds, S2 graduates to the forward shadow & sizing ramp (`10% -> 25% -> 50% -> up to 70%` cap).
- **Only H4 (DSR) fails**: The forward shadow decides; S2 runs forward with no further tuning.
- **W2 fails**: Yearly re-optimization does not help; drop re-optimization and run fixed S2 forward (if fixed S2 passes H1–H3 & W3).
- **H1, H2, H3, or W3 fails**: S2 is archived as research. The core fund stays as-is and the 15–18% fund target is reset.
