# Factor-ETF Market-Neutral Test: Data Coverage Report

**Audit Timestamp**: 2026-11-15 10:25:25 UTC  
**Declared Trial Family**: $N = 5$ (`SPLV`, `USMV`, `QUAL`, `VLUE`, `MTUM`)  
**Hedge Instrument**: `SPY`  
**Control Benchmark Set**: 15 Control ETFs (11 Sectors + `MDY`, `IWM`, `QQQ`, `DIA`)  

---

## Factor Candidates & Controls Matrix

| Ticker | Group | Name | Expected Inception | Observed Inception | Latest Date | Total Bars | Missing vs SPY | NaN Open/Close |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | Hedge Benchmark | SPDR S&P 500 ETF Trust | 1993-01-29 | 1998-12-01 | 2026-11-13 | 7032 | 0 | 0 |
| SPLV | Factor Candidate (F1) | Invesco S&P 500 Low Volatility ETF | 2011-05-05 | 2011-05-05 | 2026-11-13 | 3906 | 0 | 0 |
| USMV | Factor Candidate (F2) | iShares MSCI USA Min Vol Factor ETF | 2011-10-20 | 2011-10-20 | 2026-11-13 | 3789 | 0 | 0 |
| QUAL | Factor Candidate (F3) | iShares MSCI USA Quality Factor ETF | 2013-07-18 | 2013-07-18 | 2026-11-13 | 3353 | 0 | 0 |
| VLUE | Factor Candidate (F4) | iShares MSCI USA Value Factor ETF | 2013-04-18 | 2013-04-18 | 2026-11-13 | 3416 | 0 | 0 |
| MTUM | Factor Candidate (F5) | iShares MSCI USA Momentum Factor ETF | 2013-04-18 | 2013-04-18 | 2026-11-13 | 3416 | 0 | 0 |
| XLB | Sector & Control | Materials Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLE | Sector & Control | Energy Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLF | Sector & Control | Financial Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLI | Sector & Control | Industrial Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLK | Sector & Control | Technology Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLP | Sector & Control | Consumer Staples Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLU | Sector & Control | Utilities Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLV | Sector & Control | Health Care Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLY | Sector & Control | Consumer Discretionary Select Sector SPDR | 1998-12-22 | 1998-12-22 | 2026-11-13 | 7017 | 0 | 0 |
| XLRE | Sector & Control | Real Estate Select Sector SPDR | 2015-10-08 | 2015-10-08 | 2026-11-13 | 2792 | 0 | 0 |
| XLC | Sector & Control | Communication Services Select Sector SPDR | 2018-06-19 | 2018-06-19 | 2026-11-13 | 2114 | 0 | 0 |
| MDY | Size/Style Control | SPDR S&P MidCap 400 ETF Trust | 1995-05-04 | 1995-05-04 | 2026-11-13 | 7936 | 0 | 0 |
| IWM | Size/Style Control | iShares Russell 2000 ETF | 2000-05-26 | 2000-05-26 | 2026-11-13 | 6657 | 0 | 0 |
| QQQ | Size/Style Control | Invesco QQQ Trust (Nasdaq 100) | 1999-03-10 | 1999-03-10 | 2026-11-13 | 6965 | 0 | 0 |
| DIA | Size/Style Control | SPDR Dow Jones Industrial Average ETF | 1998-01-20 | 1998-01-20 | 2026-11-13 | 7251 | 0 | 0 |

---

## In-Sample Warm-Up and Historical Window

All candidates undergo a mandatory **126 trading day (~6 month)** rolling beta warm-up from their real inception date:
- **SPLV**: Active trading begins after warm-up on **2011-11-02**.
- **USMV**: Active trading begins after warm-up on **2012-04-24**.
- **VLUE**: Active trading begins after warm-up on **2013-10-18**.
- **MTUM**: Active trading begins after warm-up on **2013-10-18**.
- **QUAL**: Active trading begins after warm-up on **2014-01-17**.

In-sample testing runs strictly through **2022-12-30**.