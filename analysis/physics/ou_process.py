"""
Ornstein-Uhlenbeck mean-reversion model for price analysis.

Fits the continuous-time OU process to log-prices via OLS regression of
first differences on lagged levels, then derives half-life, equilibrium
mean, and actionable trading signals.
"""

import numpy as np
import pandas as pd

from config.settings import OU_HALFLIFE_MAX_MINUTES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fit_ou_parameters(prices: pd.Series) -> dict:
    """Estimate Ornstein-Uhlenbeck parameters from a price series.

    Method
    ------
    1. Compute log prices: y = ln(price).
    2. Regress delta_y on lagged_y via OLS:
           delta_y_t = a + b * y_{t-1} + epsilon
       where b < 0 implies mean reversion.
    3. Derive continuous-time parameters:
           theta  = -b          (mean-reversion speed)
           mu     = -a / b      (long-run equilibrium in log space)
           sigma  = std(epsilon) (volatility of residuals)
           half_life_bars = -ln(2) / b

    Parameters
    ----------
    prices : pd.Series
        Close prices ordered oldest-first.

    Returns
    -------
    dict
        Keys: theta, mu, sigma, half_life_bars.
        Values are None when the process is not mean-reverting (b >= 0).
    """
    default = {"theta": None, "mu": None, "sigma": None, "half_life_bars": None}
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 20:
            return default

        log_prices = np.log(prices.values)
        y_lag = log_prices[:-1]
        delta_y = np.diff(log_prices)

        # OLS: delta_y = a + b * y_lag
        # Design matrix [y_lag, 1]
        X = np.column_stack([y_lag, np.ones(len(y_lag))])
        # Normal equation: beta = (X'X)^{-1} X'y
        XtX = X.T @ X
        det = np.linalg.det(XtX)
        if abs(det) < 1e-15:
            return default

        beta = np.linalg.solve(XtX, X.T @ delta_y)
        b, a = beta[0], beta[1]

        if b >= 0:
            # Not mean-reverting
            return default

        theta = -b
        mu = -a / b
        residuals = delta_y - X @ beta
        sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
        half_life_bars = -np.log(2) / b

        return {
            "theta": float(theta),
            "mu": float(mu),
            "sigma": float(sigma),
            "half_life_bars": float(half_life_bars),
        }
    except Exception:
        return default


def ou_reversion_signal(prices: pd.Series) -> dict:
    """Generate a mean-reversion trading signal from OU model.

    Parameters
    ----------
    prices : pd.Series
        Close prices ordered oldest-first.

    Returns
    -------
    dict
        Keys: is_mean_reverting, half_life_minutes, distance_from_mean_sigma,
              expected_reversion_pct, signal.
    """
    default = {
        "is_mean_reverting": False,
        "half_life_minutes": None,
        "distance_from_mean_sigma": 0.0,
        "expected_reversion_pct": 0.0,
        "signal": "NEUTRAL",
    }
    try:
        params = fit_ou_parameters(prices)
        if params["theta"] is None:
            return default

        half_life_bars = params["half_life_bars"]
        # Assume 1-minute bars for minute-level data
        half_life_minutes = half_life_bars  # 1 bar = 1 minute

        if half_life_minutes > OU_HALFLIFE_MAX_MINUTES:
            return default

        # Distance from equilibrium in sigma units
        log_price = np.log(float(prices.iloc[-1]))
        mu = params["mu"]
        sigma = params["sigma"]

        if sigma == 0 or sigma is None:
            return default

        distance_sigma = (log_price - mu) / sigma

        # Expected reversion: price should move toward exp(mu)
        current_price = float(prices.iloc[-1])
        equilibrium_price = np.exp(mu)
        expected_reversion_pct = ((equilibrium_price - current_price) / current_price) * 100.0

        # Signal logic
        if distance_sigma < -1.5:
            signal = "BUY_DIP"
        elif distance_sigma > 1.5:
            signal = "SELL_SPIKE"
        else:
            signal = "NEUTRAL"

        return {
            "is_mean_reverting": True,
            "half_life_minutes": float(half_life_minutes),
            "distance_from_mean_sigma": float(distance_sigma),
            "expected_reversion_pct": float(expected_reversion_pct),
            "signal": signal,
        }
    except Exception:
        return default


def get_ou_score(prices: pd.Series) -> float:
    """Return a 0-100 score for mean-reversion opportunity quality.

    Higher scores indicate:
    - Large distance from equilibrium (opportunity)
    - Short half-life (fast reversion)
    - Confirmed mean-reverting regime

    Scoring formula
    ---------------
    distance_score = min(|distance_sigma| / 3.0, 1.0) * 50
    speed_score    = max(1 - half_life_min / OU_HALFLIFE_MAX_MINUTES, 0) * 50
    total          = distance_score + speed_score   (0-100)
    """
    try:
        sig = ou_reversion_signal(prices)
        if not sig["is_mean_reverting"]:
            return 0.0

        dist_abs = abs(sig["distance_from_mean_sigma"])
        distance_score = min(dist_abs / 3.0, 1.0) * 50.0

        hl = sig["half_life_minutes"]
        if hl is None or hl <= 0:
            speed_score = 0.0
        else:
            speed_score = max(1.0 - hl / OU_HALFLIFE_MAX_MINUTES, 0.0) * 50.0

        return float(np.clip(distance_score + speed_score, 0.0, 100.0))
    except Exception:
        return 0.0
