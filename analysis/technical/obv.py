"""
On-Balance Volume (OBV) with divergence detection.

Tracks cumulative volume flow and detects divergences between
price action and volume to identify potential reversals.
"""

import numpy as np
import pandas as pd


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """
    Compute standard On-Balance Volume.

    OBV = cumulative sum of (Volume * sign(close_change)).
    When close is unchanged, volume is not added.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain Close and Volume columns.

    Returns
    -------
    pd.Series
        On-Balance Volume series aligned with df index.
    """
    if df.empty or len(df) < 2:
        return pd.Series(np.nan, index=df.index, name="obv")

    close = df["Close"].values.astype(float)
    volume = df["Volume"].values.astype(float)

    # Direction of close change
    close_diff = np.diff(close, prepend=close[0])
    direction = np.sign(close_diff)

    # First bar has no prior reference, set direction to 0
    direction[0] = 0.0

    obv = np.cumsum(volume * direction)

    return pd.Series(obv, index=df.index, name="obv")


def detect_obv_divergence(df: pd.DataFrame, window: int = 20) -> dict:
    """
    Detect divergence between price and OBV over a rolling window.

    Bullish divergence: price makes lower low but OBV makes higher low.
    Bearish divergence: price makes higher high but OBV makes lower high.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain Close and Volume columns.
    window : int
        Lookback window for divergence detection (default 20).

    Returns
    -------
    dict
        {
            divergence_type: "BULLISH" / "BEARISH" / "NONE",
            strength: float (0.0 - 1.0)
        }
    """
    default = {"divergence_type": "NONE", "strength": 0.0}

    if df.empty or len(df) < window + 5:
        return default

    close = df["Close"].values.astype(float)
    obv = compute_obv(df).values

    if np.any(np.isnan(obv[-window:])):
        return default

    # Split window into two halves to compare "earlier" vs "recent" extremes
    half = window // 2
    if half < 2:
        return default

    recent_start = len(close) - half
    earlier_start = len(close) - window
    earlier_end = recent_start

    # Earlier and recent price/OBV segments
    price_earlier = close[earlier_start:earlier_end]
    price_recent = close[recent_start:]
    obv_earlier = obv[earlier_start:earlier_end]
    obv_recent = obv[recent_start:]

    if len(price_earlier) == 0 or len(price_recent) == 0:
        return default

    # Find highs and lows in each half
    price_earlier_high = np.max(price_earlier)
    price_recent_high = np.max(price_recent)
    price_earlier_low = np.min(price_earlier)
    price_recent_low = np.min(price_recent)

    obv_earlier_high = np.max(obv_earlier)
    obv_recent_high = np.max(obv_recent)
    obv_earlier_low = np.min(obv_earlier)
    obv_recent_low = np.min(obv_recent)

    divergence_type = "NONE"
    strength = 0.0

    # Bullish divergence: price lower low, OBV higher low
    if price_recent_low < price_earlier_low and obv_recent_low > obv_earlier_low:
        divergence_type = "BULLISH"
        # Strength based on how pronounced the divergence is
        price_range = price_earlier_high - price_earlier_low
        obv_range = obv_earlier_high - obv_earlier_low
        if price_range > 0 and obv_range > 0:
            price_div = (price_earlier_low - price_recent_low) / price_range
            obv_div = (obv_recent_low - obv_earlier_low) / obv_range
            strength = min((price_div + obv_div) / 2.0, 1.0)
        else:
            strength = 0.3

    # Bearish divergence: price higher high, OBV lower high
    elif price_recent_high > price_earlier_high and obv_recent_high < obv_earlier_high:
        divergence_type = "BEARISH"
        price_range = price_earlier_high - price_earlier_low
        obv_range = obv_earlier_high - obv_earlier_low
        if price_range > 0 and obv_range > 0:
            price_div = (price_recent_high - price_earlier_high) / price_range
            obv_div = (obv_earlier_high - obv_recent_high) / obv_range
            strength = min((price_div + obv_div) / 2.0, 1.0)
        else:
            strength = 0.3

    return {
        "divergence_type": divergence_type,
        "strength": round(max(0.0, min(strength, 1.0)), 4),
    }
