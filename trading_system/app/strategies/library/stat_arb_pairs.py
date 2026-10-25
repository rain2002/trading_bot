"""
Phase 5 Research Strategy: Statistical Arbitrage & Cointegration Pairs Trading
==============================================================================
Market-neutral and Long-Only relative-value pair trading based on Engle-Granger
cointegration, dynamic OLS hedge ratio estimation, Ornstein-Uhlenbeck half-life
analysis, and rolling Z-score mean-reversion gating.

Status: RESEARCH SANDBOX (Decoupled from live execution loop).
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint, adfuller
import statsmodels.api as sm

from trading_system.app.common.interfaces import Strategy
from trading_system.app.common.logger import get_logger

logger = get_logger("StatArbPairsStrategy")

# Curated GICS Industry Pairs (Economically linked companies sharing supply chains & customer bases)
DEFAULT_CURATED_PAIRS = [
    ("KO", "PEP"),    # Consumer Staples: Beverages
    ("V", "MA"),      # Financials: Payment Networks
    ("HD", "LOW"),    # Consumer Discretionary: Home Improvement
    ("WMT", "TGT"),   # Retail: Big Box / Superstores
    ("XOM", "CVX"),   # Energy: Integrated Oil & Gas
    ("DAL", "UAL"),   # Industrials: Airlines
    ("FDX", "UPS"),   # Industrials: Air Freight & Logistics
    ("JPM", "BAC"),   # Financials: Diversified Banking
    ("MSFT", "GOOGL"),# Info Tech / Comm Services: Hyperscale Tech
    ("CAT", "DE"),    # Industrials: Heavy Machinery & Agriculture
]


class StatArbPairsStrategy(Strategy):
    """
    Quantitative Statistical Arbitrage Engine:
      1. Tests pair cointegration via Engle-Granger two-step method (ADF on residuals).
      2. Computes the dynamic hedge ratio (beta) using ordinary least squares (OLS).
      3. Constructs the stationary spread S(t) = ln(Y) - beta * ln(X).
      4. Models mean reversion speed via Ornstein-Uhlenbeck continuous-time half-life.
      5. Generates entry, exit, and structural stop-loss signals based on rolling Z-score.
    """

    def __init__(
        self,
        pairs: Optional[List[Tuple[str, str]]] = None,
        lookback_window: int = 30,
        z_entry: float = 2.0,
        z_exit: float = 0.25,
        z_stop: float = 3.5,
        max_half_life_days: float = 60.0,
        p_value_threshold: float = 0.05,
        long_only_mode: bool = False,
    ):
        self.pairs = pairs or DEFAULT_CURATED_PAIRS
        self.lookback_window = lookback_window
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.z_stop = z_stop
        self.max_half_life_days = max_half_life_days
        self.p_value_threshold = p_value_threshold
        self.long_only_mode = long_only_mode

    @staticmethod
    def test_cointegration(y_series: pd.Series, x_series: pd.Series) -> Dict[str, Any]:
        """
        Runs Engle-Granger two-step cointegration test between two price series.
        Returns p-value, hedge ratio (beta), alpha, and cointegration boolean.
        """
        if len(y_series) < 60 or len(x_series) < 60:
            return {"is_cointegrated": False, "p_value": 1.0, "hedge_ratio": 1.0, "alpha": 0.0}

        # Align series on common dates
        aligned = pd.concat([y_series, x_series], axis=1).dropna()
        if len(aligned) < 60:
            return {"is_cointegrated": False, "p_value": 1.0, "hedge_ratio": 1.0, "alpha": 0.0}

        y = aligned.iloc[:, 0].values
        x = aligned.iloc[:, 1].values

        # Log transform prices for scale-independent percentage dynamics
        log_y = np.log(y)
        log_x = np.log(x)

        # Step 1: OLS regression log(Y) = alpha + beta * log(X)
        X_with_const = sm.add_constant(log_x)
        model = sm.OLS(log_y, X_with_const).fit()
        alpha = float(model.params[0])
        beta = float(model.params[1])

        # Step 2: ADF test on residuals
        residuals = model.resid
        try:
            adf_result = adfuller(residuals, autolag="AIC")
            p_val = float(adf_result[1])
        except Exception:
            p_val = 1.0

        is_coint = p_val < 0.05
        return {
            "is_cointegrated": is_coint,
            "p_value": round(p_val, 4),
            "hedge_ratio": round(beta, 4),
            "alpha": round(alpha, 4),
            "residuals": residuals,
        }

    @staticmethod
    def calculate_half_life(spread_series: pd.Series) -> float:
        """
        Estimates the Ornstein-Uhlenbeck mean-reversion speed (theta) and half-life:
          delta(S_t) = theta * (mu - S_{t-1}) * dt + noise
          Half-life tau = -ln(2) / lambda_slope
        """
        spread = spread_series.dropna()
        if len(spread) < 20:
            return 999.0

        lagged_spread = spread.shift(1).dropna()
        delta_spread = (spread - lagged_spread).dropna()

        lagged_aligned = lagged_spread.loc[delta_spread.index]
        X = sm.add_constant(lagged_aligned.values)
        y = delta_spread.values

        try:
            model = sm.OLS(y, X).fit()
            lambda_slope = float(model.params[1])
            if lambda_slope >= 0:
                return 999.0  # Does not mean-revert (explosive/trending)
            half_life = -np.log(2) / lambda_slope
            return float(half_life)
        except Exception:
            return 999.0

    def calculate_rolling_spread_and_zscore(
        self, y_series: pd.Series, x_series: pd.Series, hedge_ratio: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Computes the dynamic spread and rolling Z-score over the lookback window.
        """
        aligned = pd.concat([y_series, x_series], axis=1).dropna()
        aligned.columns = ["Y", "X"]
        log_y = np.log(aligned["Y"])
        log_x = np.log(aligned["X"])

        if hedge_ratio is None:
            # Fit initial hedge ratio
            X_const = sm.add_constant(log_x)
            ols = sm.OLS(log_y, X_const).fit()
            beta = float(ols.params.iloc[1])
        else:
            beta = hedge_ratio

        spread = log_y - beta * log_x
        rolling_mean = spread.rolling(window=self.lookback_window).mean()
        rolling_std = spread.rolling(window=self.lookback_window).std()

        z_score = (spread - rolling_mean) / (rolling_std + 1e-8)

        df = pd.DataFrame(
            {
                "Y": aligned["Y"],
                "X": aligned["X"],
                "spread": spread,
                "rolling_mean": rolling_mean,
                "rolling_std": rolling_std,
                "z_score": z_score,
                "hedge_ratio": beta,
            },
            index=aligned.index,
        )
        return df

    def evaluate_pair(
        self, y_series: pd.Series, x_series: pd.Series, pair_names: Tuple[str, str]
    ) -> Dict[str, Any]:
        """
        Evaluates a single pair, testing cointegration, half-life, and generating trading signals.
        """
        sym_y, sym_x = pair_names
        coint_res = self.test_cointegration(y_series, x_series)
        
        beta = coint_res["hedge_ratio"]
        df_spread = self.calculate_rolling_spread_and_zscore(y_series, x_series, hedge_ratio=beta)
        
        if df_spread.empty or df_spread["z_score"].dropna().empty:
            return {"pair": pair_names, "status": "INSUFFICIENT_DATA", "signal": 0}

        latest_z = float(df_spread["z_score"].iloc[-1])
        half_life = self.calculate_half_life(df_spread["spread"])

        # Signal state machine:
        # Long Spread: Y is undervalued relative to X -> Buy Y, Short X
        # Short Spread: Y is overvalued relative to X -> Short Y, Buy X
        signal_state = 0  # 0: Flat, 1: Long Spread, -1: Short Spread, 99: Stop-Loss
        trade_recommendations = {}

        if abs(latest_z) >= self.z_stop:
            # Structural breakdown stop-loss
            signal_state = 99
            trade_recommendations = {sym_y: "FLAT (STOP-LOSS)", sym_x: "FLAT (STOP-LOSS)"}
        elif latest_z <= -self.z_entry:
            # Spread is depressed -> Long Y, Short X
            signal_state = 1
            if self.long_only_mode:
                trade_recommendations = {sym_y: "BUY (OVERSOLD LAGGARD)", sym_x: "CASH"}
            else:
                trade_recommendations = {sym_y: "BUY (LONG LEG)", sym_x: "SELL_SHORT (SHORT LEG)"}
        elif latest_z >= self.z_entry:
            # Spread is inflated -> Short Y, Long X
            signal_state = -1
            if self.long_only_mode:
                trade_recommendations = {sym_y: "CASH", sym_x: "BUY (OVERSOLD LAGGARD)"}
            else:
                trade_recommendations = {sym_y: "SELL_SHORT (SHORT LEG)", sym_x: "BUY (LONG LEG)"}
        elif abs(latest_z) <= self.z_exit:
            # Mean normalized -> Flat / Take profit
            signal_state = 0
            trade_recommendations = {sym_y: "FLAT (NORMALIZED)", sym_x: "FLAT (NORMALIZED)"}
        else:
            signal_state = 0
            trade_recommendations = {sym_y: "HOLD", sym_x: "HOLD"}

        return {
            "pair": pair_names,
            "is_cointegrated": coint_res["is_cointegrated"],
            "p_value": coint_res["p_value"],
            "hedge_ratio": beta,
            "half_life_days": round(half_life, 1),
            "latest_z_score": round(latest_z, 2),
            "signal_state": signal_state,
            "recommendations": trade_recommendations,
        }

    def generate_signals(self, point_in_time_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Strategy interface hook: Scans all configured pairs across the point-in-time universe.
        """
        results = {}
        for sym_y, sym_x in self.pairs:
            if sym_y not in point_in_time_data or sym_x not in point_in_time_data:
                continue

            df_y = point_in_time_data[sym_y]
            df_x = point_in_time_data[sym_x]

            if df_y.empty or df_x.empty:
                continue

            y_close = df_y["close"] if "close" in df_y.columns else df_y.iloc[:, 0]
            x_close = df_x["close"] if "close" in df_x.columns else df_x.iloc[:, 0]

            eval_res = self.evaluate_pair(y_close, x_close, (sym_y, sym_x))
            pair_key = f"{sym_y}_{sym_x}"
            results[pair_key] = eval_res

        return results
