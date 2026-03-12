"""
Z-score mean-reversion signal module.

Computes z-scores of price relative to VWAP and rolling moving averages,
then classifies the current state as oversold, overbought, or neutral.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_OBS = 20              # Minimum data points for meaningful z-score
_OVERSOLD_THRESHOLD = -1.5
_OVERBOUGHT_THRESHOLD = 1.5
_DIP_ENTRY_THRESHOLD = -1.5
_SPIKE_EXIT_THRESHOLD = 2.0


# ---------------------------------------------------------------------------
# Public API -- z-score computations
# ---------------------------------------------------------------------------

def compute_zscore_vs_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute the z-score of Close price relative to cumulative VWAP.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``Close`` and ``Volume`` columns.

    Returns
    -------
    pd.Series
        Z-score series aligned to the input index.  NaN values are
        forward-filled with 0.0.
    """
    try:
        close = df["Close"].astype(float)
        volume = df["Volume"].astype(float)

        # Cumulative VWAP
        cum_vol = volume.cumsum()
        cum_pv = (close * volume).cumsum()
        # Avoid division by zero for leading bars with zero volume
        vwap = cum_pv / cum_vol.replace(0.0, np.nan)

        deviation = close - vwap
        rolling_std = deviation.rolling(window=_MIN_OBS, min_periods=5).std()
        # Guard against zero / near-zero std
        rolling_std = rolling_std.replace(0.0, np.nan)

        zscore = (deviation / rolling_std).fillna(0.0)
        return zscore

    except Exception:
        return pd.Series(0.0, index=df.index)


def compute_zscore_vs_rolling(prices: pd.Series, window: int = 20) -> pd.Series:
    """Compute the z-score of price relative to a rolling mean.

    Parameters
    ----------
    prices : pd.Series
        Price series (close prices, oldest-first).
    window : int
        Lookback window for the rolling mean and standard deviation.

    Returns
    -------
    pd.Series
        Z-score series.  NaN values filled with 0.0.
    """
    try:
        prices = prices.astype(float)
        rolling_mean = prices.rolling(window=window, min_periods=5).mean()
        rolling_std = prices.rolling(window=window, min_periods=5).std()
        rolling_std = rolling_std.replace(0.0, np.nan)

        zscore = ((prices - rolling_mean) / rolling_std).fillna(0.0)
        return zscore

    except Exception:
        return pd.Series(0.0, index=prices.index)


# ---------------------------------------------------------------------------
# Public API -- composite signal
# ---------------------------------------------------------------------------

def get_zscore_signal(df: pd.DataFrame) -> dict:
    """Produce a composite mean-reversion signal from z-score analysis.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``Close`` and ``Volume`` columns.  At least
        ``_MIN_OBS`` rows recommended for reliable output.

    Returns
    -------
    dict
        zscore_vwap    : float  -- latest z-score vs VWAP.
        zscore_rolling : float  -- latest z-score vs 20-bar rolling mean.
        signal         : str    -- "OVERSOLD", "OVERBOUGHT", or "NEUTRAL".
        strength       : float  -- 0.0-1.0 normalised absolute z magnitude.
        dip_entry      : bool   -- True when composite z < -1.5 (potential
                                   mean-reversion long entry).
        spike_exit     : bool   -- True when composite z > 2.0 (potential
                                   profit-taking / exit signal).
    """
    _default = {
        "zscore_vwap": 0.0,
        "zscore_rolling": 0.0,
        "signal": "NEUTRAL",
        "strength": 0.0,
        "dip_entry": False,
        "spike_exit": False,
    }

    try:
        if df is None or len(df) < 2:
            return _default

        # Compute both z-scores
        z_vwap_series = compute_zscore_vs_vwap(df)
        z_rolling_series = compute_zscore_vs_rolling(df["Close"], window=_MIN_OBS)

        z_vwap = float(z_vwap_series.iloc[-1])
        z_rolling = float(z_rolling_series.iloc[-1])

        # Composite z-score: equal weight of both signals
        composite_z = (z_vwap + z_rolling) / 2.0

        # Classify signal
        if composite_z <= _OVERSOLD_THRESHOLD:
            signal = "OVERSOLD"
        elif composite_z >= _OVERBOUGHT_THRESHOLD:
            signal = "OVERBOUGHT"
        else:
            signal = "NEUTRAL"

        # Strength: normalise |composite_z| into [0, 1] range.
        # A |z| of 3.0 or above maps to 1.0.
        strength = min(abs(composite_z) / 3.0, 1.0)

        # Entry / exit flags
        dip_entry = composite_z < _DIP_ENTRY_THRESHOLD
        spike_exit = composite_z > _SPIKE_EXIT_THRESHOLD

        return {
            "zscore_vwap": round(z_vwap, 4),
            "zscore_rolling": round(z_rolling, 4),
            "signal": signal,
            "strength": round(strength, 4),
            "dip_entry": bool(dip_entry),
            "spike_exit": bool(spike_exit),
        }

    except Exception:
        return _default
