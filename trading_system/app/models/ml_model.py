import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib
from trading_system.app.common.logger import get_logger

logger = get_logger("MLModel")

class MLPipeline:
    def __init__(self, target_horizon_days=5, target_return_threshold=0.015):
        """
        target_horizon_days: How many days into the future we are predicting.
        target_return_threshold: The percentage gain required to label a trade as '1' (Success).
        """
        self.horizon = target_horizon_days
        self.threshold = target_return_threshold
        
        # We use a shallow Random Forest to strictly prevent overfitting on historical noise
        self.model = RandomForestClassifier(
            n_estimators=100, 
            max_depth=5, 
            random_state=42, 
            class_weight="balanced"
        )
        self.feature_cols = []
        
    def create_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates the 'y' target variable.
        If the future close price (horizon days out) is > threshold%, label = 1, else 0.
        """
        df = df.copy()
        
        # Shift close price backwards to get the future price aligned with today's row
        future_close = df['close'].shift(-self.horizon)
        future_return = (future_close - df['close']) / df['close']
        
        df['target'] = np.where(future_return > self.threshold, 1, 0)
        
        # Drop the last N rows because we don't know the future yet
        df.dropna(subset=['target'], inplace=True)
        return df

    def prepare_dataset(self, feature_df: pd.DataFrame):
        df = self.create_labels(feature_df)
        
        # Drop columns we can't use for training (raw prices and dates) to prevent extreme data leakage
        drop_cols = ['open', 'high', 'low', 'close', 'volume', 'target']
        self.feature_cols = [c for c in df.columns if c not in drop_cols]
        
        # Drop rows with NaNs (e.g. the first 200 days won't have a 200-day moving average calculated yet)
        df.dropna(subset=self.feature_cols, inplace=True)
        
        X = df[self.feature_cols]
        y = df['target']
        
        return X, y

    def train(self, X_train, y_train):
        logger.info(f"Training Random Forest on {len(X_train)} samples with {len(self.feature_cols)} features...")
        self.model.fit(X_train, y_train)
        logger.info("Training complete.")
        
    def evaluate(self, X_test, y_test):
        predictions = self.model.predict(X_test)
        acc = accuracy_score(y_test, predictions)
        logger.info(f"Out of Sample Accuracy: {acc:.2f}")
        
        report = classification_report(y_test, predictions)
        print("\n=== STRICT OUT-OF-SAMPLE ML EVALUATION ===")
        print(report)
        
        # What did the AI actually care about?
        importances = self.model.feature_importances_
        feature_importance = pd.Series(importances, index=self.feature_cols).sort_values(ascending=False)
        print("\n=== TOP 5 MOST IMPORTANT FEATURES ===")
        print(feature_importance.head(5))
        
        return acc

    def save_model(self, path="trading_system/app/models/saved_rf.pkl"):
        joblib.dump(self.model, path)
        logger.info(f"Model safely exported to {path}")
