"""
VWAP (Volume Weighted Average Price) with standard deviation bands.

Computes intraday VWAP and statistical bands for mean-reversion
and trend-following scalp strategies.
"""

import numpy as np
import pandas as pd


def compute_vwap_bands(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute cumulative VWAP and standard deviation bands.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain High, Low, Close, Volume columns.

    Returns
    -------
    pd.DataFrame
        Original df with added columns:
        vwap, vwap_std, upper_1, lower_1, upper_2, lower_2, upper_3, lower_3.
    """
    result = df.copy()

    if df.empty or len(df) < 1:
        for col in ["vwap", "vwap_std", "upper_1", "lower_1",
                     "upper_2", "lower_2", "upper_3", "lower_3"]:
            result[col] = np.nan
        return result

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    volume = df["Volume"].values.astype(float)

    # Typical price
    tp = (high + low + close) / 3.0

    # Cumulative sums for VWAP
    tp_vol = tp * volume
    cum_tp_vol = np.cumsum(tp_vol)
    cum_vol = np.cumsum(volume)

    # Avoid division by zero
    cum_vol_safe = np.where(cum_vol == 0, np.nan, cum_vol)

    vwap = cum_tp_vol / cum_vol_safe

    # Standard deviation bands
    # Variance = cumsum(Vol * (TP - VWAP)^2) / cumsum(Vol)
    squared_dev = volume * (tp - vwap) ** 2
    cum_squared_dev = np.cumsum(squared_dev)
    variance = cum_squared_dev / cum_vol_safe
    vwap_std = np.sqrt(variance)

    result["vwap"] = vwap
    result["vwap_std"] = vwap_std
    result["upper_1"] = vwap + 1.0 * vwap_std
    result["lower_1"] = vwap - 1.0 * vwap_std
    result["upper_2"] = vwap + 2.0 * vwap_std
    result["lower_2"] = vwap - 2.0 * vwap_std
    result["upper_3"] = vwap + 3.0 * vwap_std
    result["lower_3"] = vwap - 3.0 * vwap_std

    return result


def get_vwap_position(price: float, vwap_df: pd.DataFrame) -> dict:
    """
    Determine the current price position relative to VWAP bands.

    Parameters
    ----------
    price : float
        Current price.
    vwap_df : pd.DataFrame
        DataFrame output from compute_vwap_bands (must have vwap and band columns).

    Returns
    -------
    dict
        {
            distance_pct: float,       # percent distance from VWAP
            band_position: str,        # e.g. "ABOVE_BAND2", "BETWEEN_1_2", "AT_VWAP"
            is_extended: bool,         # True if beyond 2nd std dev band
            reversion_target: float    # price target for mean reversion
        }
    """
    if vwap_df.empty:
        return {
            "distance_pct": 0.0,
            "band_position": "UNKNOWN",
            "is_extended": False,
            "reversion_target": price,
        }

    # Use latest row
    last = vwap_df.iloc[-1]
    vwap = last.get("vwap", np.nan)

    if np.isnan(vwap) or vwap == 0:
        return {
            "distance_pct": 0.0,
            "band_position": "UNKNOWN",
            "is_extended": False,
            "reversion_target": price,
        }

    upper_1 = last.get("upper_1", np.nan)
    lower_1 = last.get("lower_1", np.nan)
    upper_2 = last.get("upper_2", np.nan)
    lower_2 = last.get("lower_2", np.nan)
    upper_3 = last.get("upper_3", np.nan)
    lower_3 = last.get("lower_3", np.nan)

    distance_pct = ((price - vwap) / vwap) * 100.0

    # Determine band position
    if price >= upper_3:
        band_position = "ABOVE_BAND3"
    elif price >= upper_2:
        band_position = "ABOVE_BAND2"
    elif price >= upper_1:
        band_position = "BETWEEN_1_2"
    elif price > lower_1:
        band_position = "AT_VWAP"
    elif price > lower_2:
        band_position = "BETWEEN_1_2"
    elif price > lower_3:
        band_position = "BELOW_BAND2"
    else:
        band_position = "BELOW_BAND3"

    # Extended if beyond 2nd std dev on either side
    is_extended = price >= upper_2 or price <= lower_2

    # Reversion target: move one band closer to VWAP
    if price >= upper_3:
        reversion_target = float(upper_2)
    elif price >= upper_2:
        reversion_target = float(upper_1)
    elif price >= upper_1:
        reversion_target = float(vwap)
    elif price <= lower_3:
        reversion_target = float(lower_2)
    elif price <= lower_2:
        reversion_target = float(lower_1)
    elif price <= lower_1:
        reversion_target = float(vwap)
    else:
        reversion_target = float(vwap)

    return {
        "distance_pct": round(distance_pct, 4),
        "band_position": band_position,
        "is_extended": is_extended,
        "reversion_target": round(reversion_target, 4),
    }
