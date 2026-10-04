import pandas as pd
import numpy as np
from typing import List, Tuple
from trading_system.app.common.logger import get_logger

logger = get_logger("MLFramework")

class PurgedKFold:
    """
    Phase 18 Tool: Future ML Framework (Time-Aware Validation).
    Implements Combinatorial Purged Cross-Validation (CPCV) or standard
    Purged/Embargoed K-Fold for financial machine learning.
    
    Prevents leakage by:
    1. Purging: Removing training data whose observation window overlaps with the test set.
    2. Embargo: Adding an embargo period after the test set to prevent the model from 
       learning from the immediate subsequent price action.
    """
    
    def __init__(self, n_splits: int = 5, purge_days: int = 2, embargo_days: int = 2):
        self.n_splits = n_splits
        self.purge_days = purge_days
        self.embargo_days = embargo_days
        
    def split(self, dates: pd.DatetimeIndex) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Yields (train_indices, test_indices) ensuring strict temporal separation.
        """
        num_samples = len(dates)
        indices = np.arange(num_samples)
        
        # Calculate split boundaries
        split_indices = np.linspace(0, num_samples, self.n_splits + 1, dtype=int)
        
        splits = []
        for i in range(self.n_splits):
            test_start = split_indices[i]
            test_end = split_indices[i + 1]
            
            test_idx = indices[test_start:test_end]
            
            # Left training window (Before test set, minus purge)
            train_left_end = max(0, test_start - self.purge_days)
            train_left = indices[0:train_left_end]
            
            # Right training window (After test set, plus embargo)
            train_right_start = min(num_samples, test_end + self.embargo_days)
            train_right = indices[train_right_start:]
            
            train_idx = np.concatenate([train_left, train_right])
            
            splits.append((train_idx, test_idx))
            
        return splits

class MLModelRegistry:
    """
    Phase 18 Tool: Champion vs Challenger.
    Tracks ML Models, their hyperparameters, features, and structural superiority.
    """
    def __init__(self):
        self.models = {}
        
    def register_model(self, model_id: str, version: str, is_champion: bool, 
                       hyperparameters: dict, feature_hash: str):
        self.models[f"{model_id}_v{version}"] = {
            "is_champion": is_champion,
            "hyperparameters": hyperparameters,
            "feature_hash": feature_hash,
            "status": "ACTIVE" if is_champion else "CHALLENGER"
        }
        logger.info(f"Registered ML Model {model_id} (v{version}) as {self.models[f'{model_id}_v{version}']['status']}")
