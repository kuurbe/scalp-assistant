"""
Fibonacci retracement and extension levels.

Detects swing points from OHLCV data and computes standard
Fibonacci retracement and extension levels for key support/resistance zones.
"""

import numpy as np
import pandas as pd


# Standard Fibonacci ratios
RETRACEMENT_RATIOS = [0.236, 0.382, 0.5, 0.618, 0.786]
EXTENSION_RATIOS = [1.0, 1.272, 1.618, 2.0]


def detect_swing_points(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Detect the most recent swing high and swing low using rolling extremes.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain High and Low columns.
    lookback : int
        Rolling window for finding local extremes (default 20).

    Returns
    -------
    dict
        {
            swing_high: (price, index) or None,
            swing_low: (price, index) or None
        }
        index is the integer position within the DataFrame.
    """
    result = {"swing_high": None, "swing_low": None}

    if df.empty or len(df) < lookback:
        return result

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    n = len(high)

    # Find swing highs: bars where High is the max in the surrounding window
    # A swing high at index i means high[i] == max(high[i-lookback//2 : i+lookback//2+1])
    half = lookback // 2
    swing_high_price = None
    swing_high_idx = None
    swing_low_price = None
    swing_low_idx = None

    # Scan from recent to older to find the most recent swing points
    for i in range(n - 1, half - 1, -1):
        left = max(0, i - half)
        right = min(n, i + half + 1)

        if swing_high_idx is None:
            window_max = np.max(high[left:right])
            if high[i] == window_max and right - left >= half + 1:
                swing_high_price = float(high[i])
                swing_high_idx = i

        if swing_low_idx is None:
            window_min = np.min(low[left:right])
            if low[i] == window_min and right - left >= half + 1:
                swing_low_price = float(low[i])
                swing_low_idx = i

        if swing_high_idx is not None and swing_low_idx is not None:
            break

    if swing_high_price is not None:
        result["swing_high"] = (swing_high_price, swing_high_idx)
    if swing_low_price is not None:
        result["swing_low"] = (swing_low_price, swing_low_idx)

    return result


def compute_fibonacci_levels(swing_high: float, swing_low: float) -> dict:
    """
    Compute Fibonacci retracement and extension levels.

    Retracements are measured from the swing high down toward the swing low.
    Extensions project beyond the swing high.

    Parameters
    ----------
    swing_high : float
        The swing high price.
    swing_low : float
        The swing low price.

    Returns
    -------
    dict
        {
            retracements: [(ratio, price), ...],
            extensions: [(ratio, price), ...]
        }
    """
    sh = float(swing_high)
    sl = float(swing_low)
    diff = sh - sl

    # Retracements: from swing_high, pulling back toward swing_low
    # Level = swing_high - ratio * diff
    retracements = []
    for ratio in RETRACEMENT_RATIOS:
        price = sh - ratio * diff
        retracements.append((ratio, round(price, 6)))

    # Extensions: projecting beyond the swing high from the swing low
    # Level = swing_low + ratio * diff  (for ratios > 1.0, this goes above swing_high)
    extensions = []
    for ratio in EXTENSION_RATIOS:
        price = sl + ratio * diff
        extensions.append((ratio, round(price, 6)))

    return {
        "retracements": retracements,
        "extensions": extensions,
    }


def get_nearby_fib_levels(
    price: float,
    fib_levels: dict,
    tolerance_pct: float = 0.5,
) -> list:
    """
    Find Fibonacci levels near the current price.

    Parameters
    ----------
    price : float
        Current price.
    fib_levels : dict
        Output of compute_fibonacci_levels with 'retracements' and 'extensions' keys.
    tolerance_pct : float
        Percentage tolerance for proximity (default 0.5%).

    Returns
    -------
    list[dict]
        Each entry: {type, ratio, level, distance_pct, role}
        where type is "retracement" or "extension" and
        role is "SUPPORT" or "RESISTANCE".
        Sorted by absolute distance ascending.
    """
    if price <= 0:
        return []

    threshold = tolerance_pct / 100.0
    nearby = []

    for level_type in ["retracements", "extensions"]:
        levels = fib_levels.get(level_type, [])
        for ratio, level_price in levels:
            abs_distance_ratio = abs(level_price - price) / price
            if abs_distance_ratio <= threshold:
                distance_pct = (level_price - price) / price * 100.0
                role = "RESISTANCE" if level_price >= price else "SUPPORT"

                nearby.append({
                    "type": level_type.rstrip("s"),  # "retracement" or "extension"
                    "ratio": ratio,
                    "level": round(level_price, 6),
                    "distance_pct": round(distance_pct, 4),
                    "role": role,
                })

    nearby.sort(key=lambda x: abs(x["distance_pct"]))
    return nearby
