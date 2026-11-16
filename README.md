# Multi-Bot Paper Trading State Branch

This branch (origin/state) is an isolated, machine-maintained branch dedicated exclusively to persisting daily incubation state and telemetry for the frozen 3-bot core:
1. **Bot 1 (ETF & Gold Bot)**: 	rading_system/data/etf_gold_{state.json, trades.csv, equity_log.csv}
2. **Bot 2 (Bond & Cash Bot)**: 	rading_system/data/bond_cash_{state.json, trades.csv, equity_log.csv}
3. **Central Portfolio Manager**: 	rading_system/data/manager_{state.json, equity_log.csv}, unitized_nav_ledger.json

All legacy dual-pod workflow files, historical cache parquet files, and obsolete paper state files have been cleaned up.
