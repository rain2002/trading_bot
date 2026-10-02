import os

dirs = [
    "trading_system/app/config",
    "trading_system/app/data",
    "trading_system/app/features",
    "trading_system/app/strategies",
    "trading_system/app/portfolio",
    "trading_system/app/risk",
    "trading_system/app/execution",
    "trading_system/app/broker",
    "trading_system/app/backtesting",
    "trading_system/app/paper",
    "trading_system/app/live",
    "trading_system/app/accounting",
    "trading_system/app/monitoring",
    "trading_system/app/reporting",
    "trading_system/app/research",
    "trading_system/app/models",
    "trading_system/app/common",
    "trading_system/tests/unit",
    "trading_system/tests/integration",
    "trading_system/tests/backtest",
    "trading_system/tests/leakage",
    "trading_system/tests/execution",
    "trading_system/tests/risk",
    "trading_system/tests/reconciliation",
    "trading_system/migrations",
    "trading_system/scripts",
    "trading_system/notebooks",
    "trading_system/configs",
    "trading_system/data/raw",
    "trading_system/data/processed",
    "trading_system/data/features",
    "trading_system/reports",
    "trading_system/docs",
    "trading_system/docker"
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    
    # Add __init__.py for python packages
    if "app" in d or "tests" in d:
        init_file = os.path.join(d, "__init__.py")
        with open(init_file, "w") as f:
            pass

print("Repository structure scaffolded successfully.")
