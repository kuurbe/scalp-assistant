"""
ATR-based stops, targets, and position sizing.

Computes Average True Range using Wilder's smoothing and derives
dynamic stop-loss/take-profit levels and risk-managed position sizes.
"""

import math

import numpy as np
import pandas as pd


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range using Wilder's smoothing (EWM).

    True Range = max(H-L, |H-prevC|, |L-prevC|).
    ATR = EWM of TR with alpha = 1/period (Wilder's method).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain High, Low, Close columns.
    period : int
        Smoothing period (default 14).

    Returns
    -------
    pd.Series
        ATR values aligned with df index.
    """
    if df.empty or len(df) < 2:
        return pd.Series(np.nan, index=df.index, name="atr")

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)

    # True Range components
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing: EWM with alpha = 1/period
    atr = true_range.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    atr.name = "atr"
    return atr


def get_dynamic_stops(
    price: float,
    atr: float,
    direction: str = "LONG",
    stop_mult: float = 1.5,
    target_mult: float = 3.0,
) -> dict:
    """
    Compute ATR-based stop-loss and take-profit levels.

    Parameters
    ----------
    price : float
        Current entry price.
    atr : float
        Current ATR value.
    direction : str
        Trade direction: "LONG" or "SHORT".
    stop_mult : float
        ATR multiplier for stop distance (default 1.5).
    target_mult : float
        ATR multiplier for target distance (default 3.0).

    Returns
    -------
    dict
        {
            stop: float,         # stop-loss price
            target: float,       # take-profit price
            risk_reward: float,  # reward-to-risk ratio
            atr_pct: float       # ATR as percentage of price
        }
    """
    if price <= 0 or atr <= 0:
        return {
            "stop": 0.0,
            "target": 0.0,
            "risk_reward": 0.0,
            "atr_pct": 0.0,
        }

    if np.isnan(atr):
        return {
            "stop": 0.0,
            "target": 0.0,
            "risk_reward": 0.0,
            "atr_pct": 0.0,
        }

    stop_distance = atr * stop_mult
    target_distance = atr * target_mult

    direction_upper = direction.upper().strip()

    if direction_upper == "LONG":
        stop = price - stop_distance
        target = price + target_distance
    elif direction_upper == "SHORT":
        stop = price + stop_distance
        target = price - target_distance
    else:
        # Default to LONG behavior
        stop = price - stop_distance
        target = price + target_distance

    # Risk-reward ratio
    risk = abs(price - stop)
    reward = abs(target - price)
    risk_reward = reward / risk if risk > 0 else 0.0

    atr_pct = (atr / price) * 100.0

    return {
        "stop": round(stop, 6),
        "target": round(target, 6),
        "risk_reward": round(risk_reward, 4),
        "atr_pct": round(atr_pct, 4),
    }


def compute_position_size(
    account: float,
    risk_pct: float,
    entry: float,
    stop: float,
) -> dict:
    """
    Compute risk-managed position size.

    Parameters
    ----------
    account : float
        Total account value in dollars.
    risk_pct : float
        Maximum risk per trade as a percentage (e.g., 1.0 for 1%).
    entry : float
        Planned entry price.
    stop : float
        Planned stop-loss price.

    Returns
    -------
    dict
        {
            shares: int,        # number of shares to trade
            risk_dollars: float, # total dollar risk
            max_loss_pct: float  # actual portfolio risk percentage
        }
    """
    if account <= 0 or risk_pct <= 0 or entry <= 0:
        return {"shares": 0, "risk_dollars": 0.0, "max_loss_pct": 0.0}

    risk_per_share = abs(entry - stop)

    if risk_per_share == 0:
        return {"shares": 0, "risk_dollars": 0.0, "max_loss_pct": 0.0}

    # Maximum dollars to risk
    max_risk_dollars = account * (risk_pct / 100.0)

    # Number of shares (floor to avoid exceeding risk budget)
    shares = int(math.floor(max_risk_dollars / risk_per_share))

    if shares <= 0:
        return {"shares": 0, "risk_dollars": 0.0, "max_loss_pct": 0.0}

    # Actual risk
    risk_dollars = shares * risk_per_share
    max_loss_pct = (risk_dollars / account) * 100.0

    return {
        "shares": shares,
        "risk_dollars": round(risk_dollars, 2),
        "max_loss_pct": round(max_loss_pct, 4),
    }
