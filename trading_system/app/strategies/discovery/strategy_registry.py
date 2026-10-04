from typing import Dict, Type
from trading_system.app.common.interfaces import Strategy
from trading_system.app.strategies.library.t001_moving_average import T001_MovingAverageTrend
from trading_system.app.strategies.library.mr001_mean_reversion import MR001_MeanReversion
from trading_system.app.strategies.library.ensemble_regime_switch import EnsembleRegimeSwitch
from trading_system.app.strategies.library.ml001_random_forest import ML001_RandomForest
from trading_system.app.strategies.library.debug001_random_walk import DEBUG001_RandomWalk

class StrategyRegistry:
    """
    V2 Strategy Organization Module.
    Categorizes strategies into strict deployment tiers to prevent untested code
    from entering Live execution.
    """
    
    # Fully validated, WFO-tested strategies cleared for Live/Paper Canary execution
    ESTABLISHED: Dict[str, Type[Strategy]] = {
        "T001_MovingAverage": T001_MovingAverageTrend,
    }
    
    # Experimental strategies currently undergoing Research / Walk-Forward Optimization
    HYPOTHESIS: Dict[str, Type[Strategy]] = {
        "MR001_MeanReversion": MR001_MeanReversion,
        "ENS001_RegimeSwitch": EnsembleRegimeSwitch,
        "ML001_RandomForest": ML001_RandomForest,
    }
    
    # Internal tools, debugging, or strategies that failed holdout validation
    QUARANTINE: Dict[str, Type[Strategy]] = {
        "DEBUG_RandomWalk": DEBUG001_RandomWalk,
    }

    @classmethod
    def get_strategy(cls, strategy_name: str) -> Type[Strategy]:
        if strategy_name in cls.ESTABLISHED:
            return cls.ESTABLISHED[strategy_name]
        if strategy_name in cls.HYPOTHESIS:
            return cls.HYPOTHESIS[strategy_name]
        if strategy_name in cls.QUARANTINE:
            return cls.QUARANTINE[strategy_name]
        raise ValueError(f"Strategy {strategy_name} not found in any Registry Tier.")
