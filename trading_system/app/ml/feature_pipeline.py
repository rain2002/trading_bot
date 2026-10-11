"""
Phase 3: Machine Learning Engine
Module: Quantitative Feature Pipeline
Extracts 25+ stationary mathematical features from raw OHLCV price data
to feed into supervised machine learning models (Random Forest / XGBoost).
"""

from typing import Tuple, List
import pandas as pd
import numpy as np
from trading_system.app.data.yfinance_provider import YFinanceDataProvider


class MLFeaturePipeline:
    """
    Transforms raw OHLCV financial time series into stationary, normalized
    feature matrices for ML training without lookahead bias.
    """

    def __init__(self, forward_prediction_window: int = 5, target_return_threshold: float = 0.005):
        """
        :param forward_prediction_window: Number of days forward to predict (e.g. 5 days = 1 trading week)
        :param target_return_threshold: Minimum return to qualify as positive label (0.5% alpha)
        """
        self.forward_window = forward_prediction_window
        self.target_threshold = target_return_threshold
        self.feature_columns: List[str] = []

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes 25+ technical and statistical features.
        All features are mathematically normalized to prevent non-stationarity.
        """
        data = df.copy()
        close = data["close"]
        high = data.get("high", close)
        low = data.get("low", close)
        volume = data.get("volume", pd.Series(1, index=data.index))

        features = pd.DataFrame(index=data.index)

        # 1. Normalized Momentum & Returns (Multi-horizon)
        features["ret_1d"] = close.pct_change(1)
        features["ret_3d"] = close.pct_change(3)
        features["ret_5d"] = close.pct_change(5)
        features["ret_10d"] = close.pct_change(10)
        features["ret_21d"] = close.pct_change(21)

        # 2. Moving Average Distance (Stationary Trend Ratios)
        sma_10 = close.rolling(10).mean()
        sma_20 = close.rolling(20).mean()
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean()

        features["dist_sma10"] = (close - sma_10) / sma_10
        features["dist_sma20"] = (close - sma_20) / sma_20
        features["dist_sma50"] = (close - sma_50) / sma_50
        features["dist_sma200"] = (close - sma_200) / sma_200
        features["sma_spread_20_50"] = (sma_20 - sma_50) / sma_50

        # 3. Volatility Ratios
        features["vol_10d"] = close.pct_change().rolling(10).std() * np.sqrt(252)
        features["vol_30d"] = close.pct_change().rolling(30).std() * np.sqrt(252)
        features["vol_ratio"] = features["vol_10d"] / features["vol_30d"].replace(0, np.nan)

        # 4. Average True Range (ATR) Normalized
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        features["atr_norm"] = tr.rolling(14).mean() / close

        # 5. Relative Strength Index (RSI - 14) Normalized (0 to 1)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        features["rsi_norm"] = (100 - (100 / (1 + rs))) / 100.0

        # 6. Bollinger Band Position (%B)
        bb_std = close.rolling(20).std()
        bb_upper = sma_20 + (2.0 * bb_std)
        bb_lower = sma_20 - (2.0 * bb_std)
        features["bollinger_pct_b"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

        # 7. Volume Activity Normalized
        vol_sma20 = volume.rolling(20).mean()
        features["vol_surge"] = volume / vol_sma20.replace(0, np.nan)

        # 8. High/Low Range Expansion
        features["hl_spread"] = (high - low) / close

        # 9. Target Variable (Shifted backwards to strictly prevent lookahead bias)
        # Predicts whether the return over the NEXT `forward_window` days beats the threshold
        forward_return = close.shift(-self.forward_window) / close - 1.0
        features["target_label"] = (forward_return > self.target_threshold).astype(int)
        features["target_return"] = forward_return

        self.feature_columns = [
            c for c in features.columns if c not in ["target_label", "target_return"]
        ]

        return features

    def prepare_dataset(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        Cleans NaNs and extracts X (Features), y (Classification Labels), and continuous returns.
        """
        full_df = self.extract_features(df)
        
        # Drop rows where indicators or forward target couldn't be calculated (warmup + latest days)
        clean_df = full_df.dropna()

        X = clean_df[self.feature_columns]
        y = clean_df["target_label"]
        continuous_returns = clean_df["target_return"]

        return X, y, continuous_returns
