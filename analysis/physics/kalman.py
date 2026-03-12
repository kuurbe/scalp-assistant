"""
Kalman filter for price smoothing and trend estimation.

Implements a pure-numpy 1D Kalman filter (no pykalman dependency) to
produce a smoothed price series and derive trend signals from the
filtered output.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core Kalman filter
# ---------------------------------------------------------------------------

def kalman_smooth(
    prices: pd.Series,
    process_noise: float = 1e-5,
    measurement_noise: float = 1e-2,
) -> pd.Series:
    """Apply a 1D Kalman filter to a price series.

    State model (scalar):
        Prediction:  x_pred = x_prev        (random-walk prior)
                     P_pred = P_prev + Q
        Update:      K      = P_pred / (P_pred + R)
                     x      = x_pred + K * (observation - x_pred)
                     P      = (1 - K) * P_pred

    Parameters
    ----------
    prices : pd.Series
        Raw close prices, ordered oldest-first.
    process_noise : float
        Process noise variance Q.  Larger values make the filter more
        responsive (less smooth).
    measurement_noise : float
        Measurement noise variance R.  Larger values make the filter
        smoother (trusts observations less).

    Returns
    -------
    pd.Series
        Kalman-smoothed price series with the same index as *prices*.
    """
    try:
        prices = prices.astype(float)
        values = prices.values.copy()
        n = len(values)

        if n == 0:
            return prices.copy()

        # Find the first non-NaN value to initialise
        first_valid_idx = 0
        while first_valid_idx < n and np.isnan(values[first_valid_idx]):
            first_valid_idx += 1

        if first_valid_idx >= n:
            return prices.copy()

        Q = process_noise
        R = measurement_noise

        # Initialise state
        x = values[first_valid_idx]
        P = 1.0  # Initial uncertainty

        smoothed = np.full(n, np.nan)
        smoothed[first_valid_idx] = x

        for i in range(first_valid_idx + 1, n):
            obs = values[i]

            # Predict step
            x_pred = x
            P_pred = P + Q

            if np.isnan(obs):
                # No observation: carry prediction forward
                x = x_pred
                P = P_pred
            else:
                # Update step
                K = P_pred / (P_pred + R)
                x = x_pred + K * (obs - x_pred)
                P = (1.0 - K) * P_pred

            smoothed[i] = x

        return pd.Series(smoothed, index=prices.index, name="kalman_price")
    except Exception:
        return prices.copy()


# ---------------------------------------------------------------------------
# Trend signal
# ---------------------------------------------------------------------------

def kalman_trend_signal(prices: pd.Series) -> dict:
    """Derive trend direction and strength from Kalman-filtered prices.

    Parameters
    ----------
    prices : pd.Series
        Raw close prices.

    Returns
    -------
    dict
        Keys: kalman_price, kalman_velocity, trend, trend_strength.
    """
    default = {
        "kalman_price": None,
        "kalman_velocity": 0.0,
        "trend": "FLAT",
        "trend_strength": 0.0,
    }
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < 5:
            return default

        smoothed = kalman_smooth(prices)
        smoothed_clean = smoothed.dropna()

        if len(smoothed_clean) < 2:
            return default

        kalman_price = float(smoothed_clean.iloc[-1])

        # Velocity: first difference of smoothed series
        velocity_series = smoothed_clean.diff().dropna()
        if len(velocity_series) == 0:
            return {**default, "kalman_price": kalman_price}

        kalman_velocity = float(velocity_series.iloc[-1])

        # Trend strength: consistency of velocity direction over a lookback
        lookback = min(20, len(velocity_series))
        recent_vel = velocity_series.iloc[-lookback:]

        if len(recent_vel) == 0:
            return {
                "kalman_price": kalman_price,
                "kalman_velocity": kalman_velocity,
                "trend": "FLAT",
                "trend_strength": 0.0,
            }

        # Fraction of recent bars where velocity has the same sign as current
        current_sign = np.sign(kalman_velocity)
        if current_sign == 0:
            trend = "FLAT"
            trend_strength = 0.0
        else:
            same_sign_frac = float(np.mean(np.sign(recent_vel.values) == current_sign))
            # Normalise magnitude relative to price level for comparability
            price_level = abs(kalman_price) if kalman_price != 0 else 1.0
            magnitude = abs(kalman_velocity) / price_level
            # Combine consistency and magnitude
            # magnitude contribution capped at a sensible range
            mag_score = min(magnitude * 1000.0, 1.0)
            trend_strength = float(np.clip(
                0.6 * same_sign_frac + 0.4 * mag_score,
                0.0,
                1.0,
            ))

            if current_sign > 0:
                trend = "UP"
            else:
                trend = "DOWN"

            # Override to FLAT if trend strength is negligible
            if trend_strength < 0.15:
                trend = "FLAT"

        return {
            "kalman_price": kalman_price,
            "kalman_velocity": kalman_velocity,
            "trend": trend,
            "trend_strength": round(trend_strength, 4),
        }
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def get_kalman_score(prices: pd.Series) -> float:
    """Return a 0-100 score based on Kalman trend strength and consistency.

    Scoring
    -------
    Base = trend_strength * 100  (already 0-1, maps to 0-100).
    Penalise FLAT trends to 0.

    Parameters
    ----------
    prices : pd.Series
        Close prices ordered oldest-first.

    Returns
    -------
    float
        Score in [0, 100].
    """
    try:
        sig = kalman_trend_signal(prices)

        if sig["trend"] == "FLAT":
            return 0.0

        strength = sig["trend_strength"]
        score = strength * 100.0
        return float(np.clip(score, 0.0, 100.0))
    except Exception:
        return 0.0
