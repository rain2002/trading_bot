import pandas as pd
import numpy as np
from typing import Dict
from trading_system.app.common.interfaces import Strategy
from trading_system.app.common.logger import get_logger
from trading_system.app.models.ml_framework import PurgedKFold, MLModelRegistry
from sklearn.ensemble import RandomForestClassifier
import pandas_ta as ta

logger = get_logger("ML001_RandomForest")

class ML001_RandomForest(Strategy):
    """
    Phase 18 Implementation: Machine Learning Strategy using Random Forest.
    Features: RSI, MACD, ATR, Bollinger Band Position.
    Target: 1-day forward return > 0.
    """
    def __init__(self, n_estimators: int = 100, max_depth: int = 5, train_lookback_days: int = 252 * 3):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.train_lookback_days = train_lookback_days
        self.models = {} # sym -> trained model
        self.features_list = ['rsi', 'macd', 'atr', 'bb_pos']
        self.registry = MLModelRegistry()
        
    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        calc_close = df['adj_close'] if 'adj_close' in df.columns else df['close']
        
        df['rsi'] = ta.rsi(calc_close, length=14)
        macd = ta.macd(calc_close, fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df['macd'] = macd.iloc[:, 0]
        else:
            df['macd'] = 0.0
            
        df['atr'] = ta.atr(df['high'], df['low'], calc_close, length=14)
        
        bbands = ta.bbands(calc_close, length=20, std=2.0)
        if bbands is not None and not bbands.empty:
            lower = bbands.iloc[:, 0]
            upper = bbands.iloc[:, 2]
            # bb_pos: 0 = at lower band, 1 = at upper band
            df['bb_pos'] = (calc_close - lower) / (upper - lower + 1e-9)
        else:
            df['bb_pos'] = 0.5
            
        return df.dropna()

    def _train_model(self, sym: str, df: pd.DataFrame):
        features_df = self._create_features(df)
        if len(features_df) < 50:
            return False
            
        # Target: Did the price go up the next day?
        features_df['target'] = (features_df['close'].shift(-1) > features_df['close']).astype(int)
        features_df = features_df.dropna()
        
        if len(features_df) < 50:
            return False
            
        X = features_df[self.features_list].values
        y = features_df['target'].values
        
        # We use PurgedKFold in research, but for actual strategy execution we train on all available lookback
        model = RandomForestClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, random_state=42)
        model.fit(X, y)
        self.models[sym] = model
        
        # Register in Phase 18 Registry
        self.registry.register_model(
            model_id=f"RF_{sym}", 
            version="1.0", 
            is_champion=True,
            hyperparameters={"n_estimators": self.n_estimators, "max_depth": self.max_depth},
            feature_hash="rsi_macd_atr_bb"
        )
        return True

    def generate_signals(self, point_in_time_universe: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        signals = {}
        
        for sym, df in point_in_time_universe.items():
            if len(df) < 30:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                continue
                
            # Retrain model if not exists
            if sym not in self.models:
                success = self._train_model(sym, df.tail(self.train_lookback_days))
                if not success:
                    signals[sym] = {'signal': 0, 'confidence': 0.0}
                    continue
                    
            # Predict latest day
            features_df = self._create_features(df.tail(50))
            if features_df.empty:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                continue
                
            latest_features = features_df[self.features_list].iloc[-1].values.reshape(1, -1)
            model = self.models[sym]
            
            # Predict Probability of UP
            prob_up = model.predict_proba(latest_features)[0][1]
            
            if prob_up > 0.60:
                signals[sym] = {'signal': 1, 'confidence': prob_up}
            elif prob_up < 0.40:
                signals[sym] = {'signal': -1, 'confidence': 1 - prob_up}
            else:
                signals[sym] = {'signal': 0, 'confidence': 0.0}
                
        return signals
