"""
Cumulative Volume Delta (CVD) from OHLCV data.

Estimates buy/sell pressure from candlestick data to detect
accumulation, distribution, and institutional activity.
"""

import numpy as np
import pandas as pd


def compute_cvd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Cumulative Volume Delta from OHLCV bars.

    Uses the close-position-within-range method to estimate
    the buy/sell split of each bar's volume.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain High, Low, Close, Volume columns.

    Returns
    -------
    pd.DataFrame
        Original df with added columns: delta, cvd, buy_vol, sell_vol.
    """
    result = df.copy()

    if df.empty or len(df) < 1:
        for col in ["delta", "cvd", "buy_vol", "sell_vol"]:
            result[col] = np.nan
        return result

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    volume = df["Volume"].values.astype(float)

    bar_range = high - low

    # Buy ratio: proportion of bar attributed to buying
    # When range is zero (doji with no wicks), default to 0.5
    buy_ratio = np.where(
        bar_range == 0,
        0.5,
        (close - low) / bar_range,
    )

    # Clamp to [0, 1] for safety
    buy_ratio = np.clip(buy_ratio, 0.0, 1.0)

    # Delta: positive = net buying, negative = net selling
    delta = volume * (2.0 * buy_ratio - 1.0)

    # Cumulative volume delta
    cvd = np.cumsum(delta)

    # Decomposed buy/sell volume
    buy_vol = volume * buy_ratio
    sell_vol = volume * (1.0 - buy_ratio)

    result["delta"] = delta
    result["cvd"] = cvd
    result["buy_vol"] = buy_vol
    result["sell_vol"] = sell_vol

    return result


def get_cvd_signal(df: pd.DataFrame) -> dict:
    """
    Analyze CVD for trading signals.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame that already has cvd and delta columns
        (output of compute_cvd), plus Close.

    Returns
    -------
    dict
        {
            cvd_trend: "ACCUMULATING" / "DISTRIBUTING" / "NEUTRAL",
            price_cvd_divergence: bool,
            institutional_spike: bool,
            score: int (0-100)
        }
    """
    default = {
        "cvd_trend": "NEUTRAL",
        "price_cvd_divergence": False,
        "institutional_spike": False,
        "score": 50,
    }

    # Need cvd column; compute if missing
    if "cvd" not in df.columns:
        df = compute_cvd(df)

    if df.empty or len(df) < 5:
        return default

    cvd = df["cvd"].values.astype(float)
    close = df["Close"].values.astype(float)
    delta = df["delta"].values.astype(float)

    # Remove any leading NaN
    valid_mask = ~(np.isnan(cvd) | np.isnan(close))
    if valid_mask.sum() < 5:
        return default

    # Use the last 20 bars (or all if fewer)
    lookback = min(20, len(cvd))
    cvd_window = cvd[-lookback:]
    close_window = close[-lookback:]
    delta_window = delta[-lookback:]

    # ---- CVD trend via linear regression slope ----
    x = np.arange(lookback, dtype=float)
    x_mean = x.mean()
    cvd_mean = cvd_window.mean()

    cvd_slope_num = np.sum((x - x_mean) * (cvd_window - cvd_mean))
    cvd_slope_den = np.sum((x - x_mean) ** 2)
    cvd_slope = cvd_slope_num / cvd_slope_den if cvd_slope_den != 0 else 0.0

    # Normalize slope by average absolute delta for threshold
    avg_abs_delta = np.mean(np.abs(delta_window))
    if avg_abs_delta == 0:
        avg_abs_delta = 1.0

    normalized_slope = cvd_slope / avg_abs_delta

    if normalized_slope > 0.3:
        cvd_trend = "ACCUMULATING"
    elif normalized_slope < -0.3:
        cvd_trend = "DISTRIBUTING"
    else:
        cvd_trend = "NEUTRAL"

    # ---- Price-CVD divergence ----
    # Compare price direction vs CVD direction over the lookback
    price_change = close_window[-1] - close_window[0]
    cvd_change = cvd_window[-1] - cvd_window[0]

    # Divergence: price up but CVD down, or vice versa
    price_cvd_divergence = False
    if abs(price_change) > 0 and abs(cvd_change) > 0:
        price_direction = np.sign(price_change)
        cvd_direction = np.sign(cvd_change)
        if price_direction != cvd_direction:
            price_cvd_divergence = True

    # ---- Institutional spike detection ----
    # A spike is when the latest delta exceeds 3x the rolling average
    recent_abs_deltas = np.abs(delta_window)
    mean_delta = np.mean(recent_abs_deltas[:-1]) if lookback > 1 else avg_abs_delta
    if mean_delta == 0:
        mean_delta = 1.0

    latest_delta_abs = abs(delta_window[-1])
    institutional_spike = latest_delta_abs > 3.0 * mean_delta

    # ---- Score (0-100) ----
    score = 50

    # Trend contribution (+/- 20)
    trend_score = min(abs(normalized_slope) * 20.0, 20.0)
    if cvd_trend == "ACCUMULATING":
        score += trend_score
    elif cvd_trend == "DISTRIBUTING":
        score -= trend_score

    # Divergence penalty/bonus (+/- 15)
    if price_cvd_divergence:
        # Bearish divergence (price up, CVD down) reduces score
        if price_change > 0 and cvd_change < 0:
            score -= 15
        # Bullish divergence (price down, CVD up) increases score
        elif price_change < 0 and cvd_change > 0:
            score += 15

    # Institutional spike adds conviction in direction of the spike
    if institutional_spike:
        if delta_window[-1] > 0:
            score += 15
        else:
            score -= 15

    score = int(np.clip(score, 0, 100))

    return {
        "cvd_trend": cvd_trend,
        "price_cvd_divergence": price_cvd_divergence,
        "institutional_spike": institutional_spike,
        "score": score,
    }
