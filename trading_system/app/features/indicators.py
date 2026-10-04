import pandas as pd
import pandas_ta as ta

class FeatureEngine:
    """
    Generates standard technical and statistical features for the Strategy Library and ML models.
    """
    @staticmethod
    def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close_series = df['adj_close'] if 'adj_close' in df.columns else df['close']
        
        # Relative Strength Index
        df['RSI_14'] = ta.rsi(close_series, length=14)
        
        # Moving Average Convergence Divergence
        macd = ta.macd(close_series)
        if macd is not None:
            df = pd.concat([df, macd], axis=1)
        return df
        
    @staticmethod
    def add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        high = df['adj_high'] if 'adj_high' in df.columns else df['high']
        low = df['adj_low'] if 'adj_low' in df.columns else df['low']
        close_series = df['adj_close'] if 'adj_close' in df.columns else df['close']
        
        # Average True Range
        df['ATR_14'] = ta.atr(high, low, close_series, length=14)
        
        # Bollinger Bands
        bbands = ta.bbands(close_series, length=20, std=2.0)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)
        return df
        
    @staticmethod
    def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close_series = df['adj_close'] if 'adj_close' in df.columns else df['close']
        
        # Distance from Moving Averages (useful for Mean Reversion and Trend)
        df['SMA_50'] = ta.sma(close_series, length=50)
        df['SMA_200'] = ta.sma(close_series, length=200)
        df['Dist_to_SMA50'] = (close_series - df['SMA_50']) / df['SMA_50']
        return df
