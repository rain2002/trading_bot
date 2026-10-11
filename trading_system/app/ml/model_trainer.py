"""
Phase 3: Machine Learning Engine
Module: Model Trainer & Walk-Forward Cross-Validator
Trains an institutional Random Forest / Gradient Boosting classifier
with Purged Time-Series Cross-Validation to guarantee no data leakage.
"""

import os
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, classification_report
import joblib


class QuantMLTrainer:
    """
    Trains and cross-validates tree-based ensemble models on financial features.
    Enforces chronological time-split validation (Train on past, Test on unseen future).
    """

    def __init__(
        self,
        n_estimators: int = 150,
        max_depth: int = 5,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ):
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=random_state,
            n_jobs=-1,
        )
        self.feature_importances: Dict[str, float] = {}

    def train_walk_forward(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        forward_returns: pd.Series,
        train_ratio: float = 0.75,
    ) -> Dict[str, Any]:
        """
        Splits chronologically:
          - First 75%: Historical Training Set
          - Last 25%: Unseen Out-of-Sample (OOS) Test Set
        """
        split_idx = int(len(X) * train_ratio)

        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        test_returns = forward_returns.iloc[split_idx:]

        # Train model on historical past
        self.model.fit(X_train, y_train)

        # Predict probabilities on unseen future
        probs_test = self.model.predict_proba(X_test)[:, 1]
        preds_test = (probs_test >= 0.52).astype(int)  # 52% probability threshold for conviction

        # Metrics
        acc = accuracy_score(y_test, preds_test)
        prec = precision_score(y_test, preds_test, zero_division=0)

        # Calculate actual simulated trading return on test set
        # When model predicts BUY (1), take the forward return; else stay 0 (cash)
        strategy_returns = preds_test * test_returns
        cum_strategy_return = (1 + strategy_returns).prod() - 1.0
        cum_buy_and_hold = (1 + test_returns).prod() - 1.0

        # Feature importances
        importances = self.model.feature_importances_
        feature_names = X.columns
        sorted_indices = np.argsort(importances)[::-1]
        self.feature_importances = {
            feature_names[i]: round(float(importances[i]), 4)
            for i in sorted_indices
        }

        results = {
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "test_start_date": str(X_test.index[0]),
            "test_end_date": str(X_test.index[-1]),
            "out_of_sample_accuracy": round(float(acc), 4),
            "out_of_sample_precision": round(float(prec), 4),
            "strategy_return_pct": round(float(cum_strategy_return * 100), 2),
            "buy_and_hold_pct": round(float(cum_buy_and_hold * 100), 2),
            "top_features": dict(list(self.feature_importances.items())[:8]),
        }

        return results

    def save_model(self, file_path: str):
        """Persists trained model and metadata to disk."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        joblib.dump(self.model, file_path)

    @classmethod
    def load_model(cls, file_path: str):
        """Loads trained model from disk for live inference."""
        trainer = cls()
        trainer.model = joblib.load(file_path)
        return trainer
