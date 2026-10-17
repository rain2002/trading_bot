import pandas as pd
import numpy as np
from trading_system.app.common.logger import get_logger

logger = get_logger("CorporateActions")

class CorporateActionProcessor:
    """
    Handles Stock Splits, Reverse Splits, and Cash Dividends strictly point-in-time.
    Prevents the future data leakage that occurs when using heavily retro-adjusted prices.
    """
    
    @staticmethod
    def calculate_adjustment_factors(raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes a dataframe with raw OHLC, 'dividends', and 'stock splits'.
        Calculates cumulative adjustment factors walking BACKWARDS from the end of the series,
        which is standard for creating adjusted continuous series for technical analysis.
        However, the engine will store BOTH the raw prices (for execution) and the adjusted 
        series (for signals).
        """
        df = raw_df.copy()
        
        # Ensure the required columns exist
        for col in ['dividends', 'stock splits']:
            if col not in df.columns:
                df[col] = 0.0
                
        # Fill NaNs with 0 for corporate actions
        df['dividends'] = df['dividends'].fillna(0)
        df['stock splits'] = df['stock splits'].fillna(0)
        
        # Calculate Split Factor (walking backwards)
        # If a 2:1 split happens today (ratio = 2.0), historical prices prior to today must be halved (* 0.5).
        # We invert the split ratio (1.0 / ratio) and shift(-1) so that the split applies strictly to days *before* the ex-date.
        inv_split_ratios = df['stock splits'].apply(lambda r: 1.0 / r if (pd.notnull(r) and r > 0) else 1.0)
        shifted_inv_splits = inv_split_ratios.shift(-1, fill_value=1.0)
        split_factor = shifted_inv_splits.iloc[::-1].cumprod().iloc[::-1]
        
        # We also need to adjust for dividends. 
        # (Close - Dividend) / Close gives the ratio drop caused by the dividend.
        # This requires the raw close price of the day BEFORE the dividend.
        prev_close = df['close'].shift(1)
        div_yield = (df['dividends'] / prev_close).fillna(0.0)
        div_multiplier = (1.0 - div_yield).clip(lower=0.0, upper=1.0)
        shifted_div_multiplier = div_multiplier.shift(-1, fill_value=1.0)
        div_factor = shifted_div_multiplier.iloc[::-1].cumprod().iloc[::-1]
        
        # Total Adjustment Factor
        df['adj_factor'] = split_factor * div_factor
        
        # Create the adjusted columns strictly for technical analysis / indicators
        df['adj_open'] = df['open'] * df['adj_factor']
        df['adj_high'] = df['high'] * df['adj_factor']
        df['adj_low'] = df['low'] * df['adj_factor']
        df['adj_close'] = df['close'] * df['adj_factor']
        df['adj_volume'] = df['volume'] / df['adj_factor'].replace(0.0, 1.0)
        
        logger.info(f"Calculated corporate action adjustment factors for {len(df)} rows.")
        return df

    @staticmethod
    def apply_splits_to_portfolio(current_positions: dict, today_splits: dict) -> dict:
        """
        Mutates the portfolio position sizes directly when a split ex-date is reached.
        If AAPL does a 4:1 split today, our 100 shares become 400 shares.
        """
        new_positions = current_positions.copy()
        for sym, split_ratio in today_splits.items():
            if split_ratio > 0 and sym in new_positions:
                old_qty = new_positions[sym]
                new_qty = old_qty * split_ratio
                new_positions[sym] = new_qty
                logger.info(f"CORPORATE ACTION: {sym} split {split_ratio}:1. Position updated: {old_qty} -> {new_qty}")
        return new_positions
