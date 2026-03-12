"""
Hurst exponent estimation and regime classification.

The Hurst exponent H characterises a time series:
    H > 0.5  -> trending / persistent (momentum regime)
    H ~ 0.5  -> random walk
    H < 0.5  -> mean-reverting / anti-persistent

Two estimation methods are provided (variance ratio and rescaled range)
and a combined estimator that averages them.
"""

import numpy as np
import pandas as pd

from config.settings import HURST_TREND_THRESHOLD, HURST_REVERT_THRESHOLD

# Minimum number of observations required for a reliable estimate
_MIN_OBSERVATIONS = 50


# ---------------------------------------------------------------------------
# Estimation methods
# ---------------------------------------------------------------------------

def hurst_variance(prices: pd.Series) -> float:
    """Estimate the Hurst exponent via the variance method.

    For each lag *k*, compute the standard deviation of (price[t] - price[t-k]).
    In a fractional-Brownian-motion model, std ~ k^H, so
    H = slope of log(std) vs log(k).

    Parameters
    ----------
    prices : pd.Series
        Price series (>= 50 observations).

    Returns
    -------
    float
        Estimated Hurst exponent, or 0.5 on failure.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBSERVATIONS:
            return 0.5

        values = prices.values
        n = len(values)

        # Use lags from 2 up to n//4
        max_lag = max(n // 4, 2)
        lags = np.arange(2, max_lag + 1)

        log_lags = []
        log_stds = []

        for lag in lags:
            diffs = values[lag:] - values[:-lag]
            std = np.std(diffs, ddof=1)
            if std > 0:
                log_lags.append(np.log(lag))
                log_stds.append(np.log(std))

        if len(log_lags) < 3:
            return 0.5

        log_lags = np.array(log_lags)
        log_stds = np.array(log_stds)

        # OLS: log(std) = H * log(lag) + c
        X = np.column_stack([log_lags, np.ones(len(log_lags))])
        beta = np.linalg.lstsq(X, log_stds, rcond=None)[0]
        H = float(beta[0])

        # Clamp to [0, 1]
        return float(np.clip(H, 0.0, 1.0))
    except Exception:
        return 0.5


def hurst_rs(prices: pd.Series) -> float:
    """Estimate the Hurst exponent via Rescaled Range (R/S) analysis.

    For each lag *n*, divide the series into contiguous sub-windows of
    length *n*.  In each window compute:
        R/S = (max(cumdev) - min(cumdev)) / std

    Then H = slope of log(mean R/S) vs log(n).

    Parameters
    ----------
    prices : pd.Series
        Price series (>= 50 observations).

    Returns
    -------
    float
        Estimated Hurst exponent, or 0.5 on failure.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBSERVATIONS:
            return 0.5

        values = prices.values
        n = len(values)

        # Returns (first differences)
        returns = np.diff(values)

        # Window sizes: powers of 2 up to n//2, plus some intermediate sizes
        max_window = n // 2
        min_window = 8
        if max_window < min_window:
            return 0.5

        # Generate logarithmically spaced window sizes
        num_sizes = min(20, max_window - min_window + 1)
        window_sizes = np.unique(
            np.logspace(
                np.log10(min_window),
                np.log10(max_window),
                num=num_sizes,
            ).astype(int)
        )
        window_sizes = window_sizes[window_sizes >= min_window]

        log_ns = []
        log_rs = []

        for w in window_sizes:
            num_windows = len(returns) // w
            if num_windows < 1:
                continue

            rs_values = []
            for i in range(num_windows):
                segment = returns[i * w : (i + 1) * w]
                seg_mean = np.mean(segment)
                seg_std = np.std(segment, ddof=1)
                if seg_std == 0:
                    continue
                cumdev = np.cumsum(segment - seg_mean)
                R = np.max(cumdev) - np.min(cumdev)
                rs_values.append(R / seg_std)

            if len(rs_values) > 0:
                mean_rs = np.mean(rs_values)
                if mean_rs > 0:
                    log_ns.append(np.log(w))
                    log_rs.append(np.log(mean_rs))

        if len(log_ns) < 3:
            return 0.5

        log_ns = np.array(log_ns)
        log_rs = np.array(log_rs)

        # OLS: log(R/S) = H * log(n) + c
        X = np.column_stack([log_ns, np.ones(len(log_ns))])
        beta = np.linalg.lstsq(X, log_rs, rcond=None)[0]
        H = float(beta[0])

        return float(np.clip(H, 0.0, 1.0))
    except Exception:
        return 0.5


def compute_hurst(prices: pd.Series, method: str = "both") -> float:
    """Compute the Hurst exponent using one or both methods.

    Parameters
    ----------
    prices : pd.Series
        Price series (minimum 50 data points required).
    method : str
        "variance", "rs", or "both" (default).

    Returns
    -------
    float
        Estimated Hurst exponent in [0, 1], or 0.5 as safe default.
    """
    try:
        prices = prices.astype(float).dropna()
        if len(prices) < _MIN_OBSERVATIONS:
            return 0.5

        if method == "variance":
            return hurst_variance(prices)
        elif method == "rs":
            return hurst_rs(prices)
        else:
            h_var = hurst_variance(prices)
            h_rs = hurst_rs(prices)
            return float((h_var + h_rs) / 2.0)
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_regime(H: float) -> dict:
    """Classify the market regime from a Hurst exponent.

    Parameters
    ----------
    H : float
        Hurst exponent value.

    Returns
    -------
    dict
        Keys: H, regime, confidence, preferred_strategy.
    """
    try:
        H = float(H)
    except (TypeError, ValueError):
        H = 0.5

    H = float(np.clip(H, 0.0, 1.0))

    # Determine regime
    if H >= HURST_TREND_THRESHOLD:
        regime = "TRENDING"
        preferred_strategy = "MOMENTUM"
        # Confidence based on distance from threshold
        dist = H - HURST_TREND_THRESHOLD
    elif H <= HURST_REVERT_THRESHOLD:
        regime = "MEAN_REVERTING"
        preferred_strategy = "MEAN_REVERSION"
        dist = HURST_REVERT_THRESHOLD - H
    else:
        regime = "RANDOM"
        preferred_strategy = "SKIP"
        dist = 0.0

    # Confidence tiers based on distance from the boundary
    if regime == "RANDOM":
        confidence = "LOW"
    elif dist >= 0.10:
        confidence = "HIGH"
    elif dist >= 0.05:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "H": H,
        "regime": regime,
        "confidence": confidence,
        "preferred_strategy": preferred_strategy,
    }


def get_hurst_score(prices: pd.Series) -> float:
    """Return a 0-100 score reflecting regime clarity.

    High scores are awarded for strong trending or mean-reverting signals
    with high confidence.  A random walk returns 0.

    Scoring
    -------
    RANDOM regime -> 0
    TRENDING / MEAN_REVERTING:
        base  = distance_from_0.5 * 200  (max 100 when H=0 or H=1)
        multiplier by confidence:  HIGH=1.0, MEDIUM=0.7, LOW=0.4
    """
    try:
        H = compute_hurst(prices)
        info = classify_regime(H)

        if info["regime"] == "RANDOM":
            return 0.0

        distance = abs(H - 0.5)
        base = min(distance * 200.0, 100.0)

        conf_mult = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.4}
        multiplier = conf_mult.get(info["confidence"], 0.4)

        return float(np.clip(base * multiplier, 0.0, 100.0))
    except Exception:
        return 0.0
