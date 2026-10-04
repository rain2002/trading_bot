# Quantitative Research Philosophy

This document outlines the strict methodological rules the AI Trading Engine must follow to prevent overfitting, data leakage, and curve-fitting. These principles ensure that any edge discovered is mathematically robust and likely to persist in live markets.

## 1. The Three Data Regimes
Data must be strictly partitioned to prevent the system from "learning the test".

| Period | Purpose | Allowed for Optimization? |
|---|---|---|
| **Training Set** | Develop strategies and train ML parameters | ✅ Yes |
| **Validation Set** | Tune hyper-parameters and select candidates | ✅ Yes (but cautiously) |
| **Final Holdout** | The "Surprise Exam" | ❌ NEVER |

### The Golden Rule of the Final Holdout
**Do not peek at the final test just because you are curious.**
Once a strategy's parameters are modified based on its performance in the Final Holdout, the holdout is contaminated and is no longer a valid test. If a strategy fails the Final Holdout, it is discarded. The researcher must return to the Training Set to develop a new hypothesis and eventually establish a *new* untouched holdout.

## 2. Walk-Forward Testing
Rather than a single static Train/Test split, the engine should evaluate strategies using an expanding or rolling Walk-Forward Optimization (WFO) window.

```text
TRAIN              TEST
2010 ─── 2018      2019
      ↓
2011 ─── 2019      2020
      ↓
2012 ─── 2020      2021
      ↓
2013 ─── 2021      2022
      ↓
2014 ─── 2022      2023
```
This forces the strategy to repeatedly prove it can adapt to unseen data, generating a series of "mini surprise exams" rather than relying on a single lucky time period.

## 3. The Pipeline to Production
A strategy must survive the following gauntlet before ever touching real capital:

1. **Historical Development** (Training Set)
2. **Walk-Forward Testing** (Rolling Validation)
3. **FINAL HOLDOUT** (Strictly Untouched Test Set)
4. **Paper Trading** (Live Forward-Testing)
5. **Small Live Exposure** (Production)

*Live trading itself is the ultimate out-of-sample test. You cannot optimize against tomorrow's market data before tomorrow happens.*
