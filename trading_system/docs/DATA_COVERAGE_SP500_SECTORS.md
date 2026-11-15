# S&P 500 Sector Market-Neutral Bot: Data Coverage & Integrity Report

**Audit Timestamp**: 2026-11-14 23:53:58 UTC  
**Universe**: 11 US Sector SPDR ETFs + SPY Broad Market Hedge  
**Price Basis**: Total Return (Split & Dividend Adjusted via `auto_adjust=True`)  
**Local Parquet Cache**: `trading_system/data/sp500_sectors_cache/`  

---

## 1. Summary Coverage Matrix

| Ticker | Group | Name | Expected Inception | Observed Inception | Latest Date | Total Bars | Missing vs SPY | NaN Open/Close |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| XLB | Core Nine | Materials Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLE | Core Nine | Energy Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLF | Core Nine | Financial Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLI | Core Nine | Industrial Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLK | Core Nine | Technology Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLP | Core Nine | Consumer Staples Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLU | Core Nine | Utilities Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLV | Core Nine | Health Care Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLY | Core Nine | Consumer Discretionary Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLRE | Real Estate | Real Estate Select Sector SPDR | 2015-10-08 | 2015-10-08 | 2026-11-13 | 2792 | 0 | 0 |
| XLC | Communication Services | Communication Services Select Sector SPDR | 2018-06-19 | 2018-06-19 | 2026-11-13 | 2114 | 0 | 0 |
| SPY | Hedge Instrument | SPDR S&P 500 ETF Trust | 1993-01-29 | 1998-12-01 | 2026-11-13 | 7032 | 0 | 0 |

---

## 2. Inception Dates & Cross-Sectional Ranking Dynamics

To prevent lookahead bias and survivorship distortion, ETFs enter the ranking pool strictly at their documented inception:

1. **Core Nine Era (1998-12-22 to 2015-10-07)**:  
   - Universe size: **9 sectors** (`XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY`).
   - Top 3 long leg constitutes a selection of 3 / 9 = 33.3% of available sectors.

2. **Real Estate Carve-Out (2015-10-08 to 2018-06-18)**:  
   - `XLRE` launched on 2015-10-08 (carved out of Financials).
   - For momentum ranking (requiring 12 months lookback), `XLRE` enters the candidate ranking pool on **2016-10-31**.
   - Universe expands to **10 sectors**.

3. **Communication Services Carve-Out (2018-06-19 to Present)**:  
   - `XLC` launched on 2018-06-19 (carved out of Technology and Discretionary).
   - For momentum ranking, `XLC` enters the candidate ranking pool on **2019-06-30**.
   - Universe expands to **11 sectors**.

---

## 3. Data Integrity & Usability Verdict

- **Zero Missing Days**: All sector ETFs have exactly 0 missing trading sessions relative to SPY during their active lifespans.
- **Zero NaN Values**: All open and close fields are complete and non-zero.
- **Execution Consistency**: `auto_adjust=True` adjusts both `open` and `close` identically for corporate actions, providing clean next-open fill execution modeling.