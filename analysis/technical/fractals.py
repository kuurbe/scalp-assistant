"""
Williams Fractal detection.

Identifies fractal highs and lows (5-bar reversal patterns) to
establish confirmed support and resistance levels.
"""

import numpy as np
import pandas as pd


def detect_fractals(df: pd.DataFrame, period: int = 2) -> pd.DataFrame:
    """
    Detect Williams fractals in OHLCV data.

    A fractal high occurs when a bar's High is the highest among
    the surrounding (2 * period + 1) bars.
    A fractal low occurs when a bar's Low is the lowest among
    the surrounding (2 * period + 1) bars.

    The default period of 2 gives the classic 5-bar pattern
    (2 bars on each side of the center bar).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain High and Low columns.
    period : int
        Number of bars on each side (default 2 for 5-bar fractals).

    Returns
    -------
    pd.DataFrame
        Original df with added boolean columns: fractal_high, fractal_low.
    """
    result = df.copy()
    n = len(df)

    result["fractal_high"] = False
    result["fractal_low"] = False

    if n < 2 * period + 1:
        return result

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)

    fractal_high = np.zeros(n, dtype=bool)
    fractal_low = np.zeros(n, dtype=bool)

    for i in range(period, n - period):
        # Check fractal high: center bar High must be strictly higher than
        # all surrounding bars' Highs
        is_high = True
        for j in range(1, period + 1):
            if high[i] <= high[i - j] or high[i] <= high[i + j]:
                is_high = False
                break
        fractal_high[i] = is_high

        # Check fractal low: center bar Low must be strictly lower than
        # all surrounding bars' Lows
        is_low = True
        for j in range(1, period + 1):
            if low[i] >= low[i - j] or low[i] >= low[i + j]:
                is_low = False
                break
        fractal_low[i] = is_low

    result["fractal_high"] = fractal_high
    result["fractal_low"] = fractal_low

    return result


def get_fractal_levels(df: pd.DataFrame, max_levels: int = 10) -> dict:
    """
    Extract the most recent confirmed fractal support and resistance levels.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with fractal_high and fractal_low columns
        (output of detect_fractals), plus High and Low.
    max_levels : int
        Maximum number of levels to return per side (default 10).

    Returns
    -------
    dict
        {
            resistance: [float, ...],  # most recent fractal highs (newest first)
            support: [float, ...]      # most recent fractal lows (newest first)
        }
    """
    # Compute fractals if not present
    if "fractal_high" not in df.columns or "fractal_low" not in df.columns:
        df = detect_fractals(df)

    resistance = []
    support = []

    if df.empty:
        return {"resistance": resistance, "support": support}

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    fh = df["fractal_high"].values
    fl = df["fractal_low"].values

    # Collect from most recent backward
    n = len(df)
    for i in range(n - 1, -1, -1):
        if fh[i] and len(resistance) < max_levels:
            resistance.append(round(float(high[i]), 6))
        if fl[i] and len(support) < max_levels:
            support.append(round(float(low[i]), 6))
        if len(resistance) >= max_levels and len(support) >= max_levels:
            break

    return {
        "resistance": resistance,
        "support": support,
    }
