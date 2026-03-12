"""
Candlestick pattern recognition using pure numpy/pandas.

Detects common single-bar and multi-bar reversal and continuation
patterns without any TA-Lib dependency.
"""

import numpy as np
import pandas as pd


def _bar_components(o: float, h: float, l: float, c: float) -> dict:
    """Compute body, wicks, and range for a single bar."""
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    bar_range = h - l
    is_bullish = c > o
    is_bearish = c < o
    return {
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "range": bar_range,
        "is_bullish": is_bullish,
        "is_bearish": is_bearish,
    }


def _detect_hammer(o: float, h: float, l: float, c: float) -> dict | None:
    """
    Hammer: small body at the top, long lower wick (>=2x body), tiny upper wick.
    Bullish reversal signal at the bottom of a downtrend.
    """
    comp = _bar_components(o, h, l, c)
    if comp["range"] == 0:
        return None

    body_ratio = comp["body"] / comp["range"]
    lower_ratio = comp["lower_wick"] / comp["range"]
    upper_ratio = comp["upper_wick"] / comp["range"]

    # Body should be small (<35% of range), lower wick long (>55%), upper wick small (<15%)
    if body_ratio < 0.35 and lower_ratio > 0.55 and upper_ratio < 0.15:
        strength = min(lower_ratio / 0.55, 1.0) * 0.8
        if comp["is_bullish"]:
            strength += 0.2  # Bullish close adds confidence
        return {"pattern": "hammer", "type": "BULLISH", "strength": round(strength, 4)}

    return None


def _detect_shooting_star(o: float, h: float, l: float, c: float) -> dict | None:
    """
    Shooting star: small body at the bottom, long upper wick (>=2x body), tiny lower wick.
    Bearish reversal signal at the top of an uptrend.
    """
    comp = _bar_components(o, h, l, c)
    if comp["range"] == 0:
        return None

    body_ratio = comp["body"] / comp["range"]
    upper_ratio = comp["upper_wick"] / comp["range"]
    lower_ratio = comp["lower_wick"] / comp["range"]

    if body_ratio < 0.35 and upper_ratio > 0.55 and lower_ratio < 0.15:
        strength = min(upper_ratio / 0.55, 1.0) * 0.8
        if comp["is_bearish"]:
            strength += 0.2
        return {
            "pattern": "shooting_star",
            "type": "BEARISH",
            "strength": round(strength, 4),
        }

    return None


def _detect_doji(o: float, h: float, l: float, c: float) -> dict | None:
    """
    Doji: very small body relative to range, indicating indecision.
    """
    comp = _bar_components(o, h, l, c)
    if comp["range"] == 0:
        return None

    body_ratio = comp["body"] / comp["range"]

    # Doji: body is less than 10% of range
    if body_ratio < 0.10:
        # Strength based on how small the body is and how balanced the wicks are
        wick_balance = 1.0 - abs(comp["upper_wick"] - comp["lower_wick"]) / comp["range"]
        strength = (1.0 - body_ratio / 0.10) * 0.6 + wick_balance * 0.4
        return {
            "pattern": "doji",
            "type": "BULLISH",  # Doji is neutral but slightly bullish after a downtrend
            "strength": round(min(strength, 1.0), 4),
        }

    return None


def _detect_marubozu(o: float, h: float, l: float, c: float) -> dict | None:
    """
    Marubozu: large body with very small or no wicks.
    Strong continuation/momentum signal.
    """
    comp = _bar_components(o, h, l, c)
    if comp["range"] == 0:
        return None

    body_ratio = comp["body"] / comp["range"]
    upper_ratio = comp["upper_wick"] / comp["range"]
    lower_ratio = comp["lower_wick"] / comp["range"]

    # Body should be >85% of range, wicks very small
    if body_ratio > 0.85 and upper_ratio < 0.10 and lower_ratio < 0.10:
        strength = min(body_ratio, 1.0)
        pattern_type = "BULLISH" if comp["is_bullish"] else "BEARISH"
        return {
            "pattern": "marubozu",
            "type": pattern_type,
            "strength": round(strength, 4),
        }

    return None


def _detect_bullish_engulfing(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
) -> dict | None:
    """
    Bullish engulfing: bearish bar followed by a bullish bar whose body
    completely engulfs the previous bar's body.
    """
    comp1 = _bar_components(o1, h1, l1, c1)
    comp2 = _bar_components(o2, h2, l2, c2)

    if not comp1["is_bearish"] or not comp2["is_bullish"]:
        return None

    # Second bar's body must engulf first bar's body
    body1_high = max(o1, c1)
    body1_low = min(o1, c1)
    body2_high = max(o2, c2)
    body2_low = min(o2, c2)

    if body2_high > body1_high and body2_low < body1_low:
        # Strength: how much bigger the engulfing bar is
        if comp1["body"] > 0:
            size_ratio = comp2["body"] / comp1["body"]
        else:
            size_ratio = 2.0
        strength = min(size_ratio / 3.0, 1.0)
        return {
            "pattern": "bullish_engulfing",
            "type": "BULLISH",
            "strength": round(max(strength, 0.5), 4),
        }

    return None


def _detect_bearish_engulfing(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
) -> dict | None:
    """
    Bearish engulfing: bullish bar followed by a bearish bar whose body
    completely engulfs the previous bar's body.
    """
    comp1 = _bar_components(o1, h1, l1, c1)
    comp2 = _bar_components(o2, h2, l2, c2)

    if not comp1["is_bullish"] or not comp2["is_bearish"]:
        return None

    body1_high = max(o1, c1)
    body1_low = min(o1, c1)
    body2_high = max(o2, c2)
    body2_low = min(o2, c2)

    if body2_high > body1_high and body2_low < body1_low:
        if comp1["body"] > 0:
            size_ratio = comp2["body"] / comp1["body"]
        else:
            size_ratio = 2.0
        strength = min(size_ratio / 3.0, 1.0)
        return {
            "pattern": "bearish_engulfing",
            "type": "BEARISH",
            "strength": round(max(strength, 0.5), 4),
        }

    return None


def _detect_morning_star(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
    o3: float, h3: float, l3: float, c3: float,
) -> dict | None:
    """
    Morning star: 3-bar bullish reversal.
    Bar 1: large bearish candle.
    Bar 2: small body (star) that gaps down.
    Bar 3: large bullish candle closing into bar 1's body.
    """
    comp1 = _bar_components(o1, h1, l1, c1)
    comp2 = _bar_components(o2, h2, l2, c2)
    comp3 = _bar_components(o3, h3, l3, c3)

    # Bar 1 must be bearish with a meaningful body
    if not comp1["is_bearish"] or comp1["range"] == 0:
        return None

    body1_ratio = comp1["body"] / comp1["range"]
    if body1_ratio < 0.5:
        return None

    # Bar 2 must have a small body (star)
    if comp1["range"] == 0:
        return None
    star_ratio = comp2["body"] / comp1["range"]
    if star_ratio > 0.3:
        return None

    # Bar 3 must be bullish with a meaningful body
    if not comp3["is_bullish"] or comp3["range"] == 0:
        return None

    body3_ratio = comp3["body"] / comp3["range"]
    if body3_ratio < 0.5:
        return None

    # Bar 3 close should be above midpoint of bar 1's body
    bar1_midpoint = (o1 + c1) / 2.0
    if c3 < bar1_midpoint:
        return None

    strength = min((body1_ratio + body3_ratio) / 2.0, 1.0)
    return {
        "pattern": "morning_star",
        "type": "BULLISH",
        "strength": round(strength, 4),
    }


def _detect_evening_star(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
    o3: float, h3: float, l3: float, c3: float,
) -> dict | None:
    """
    Evening star: 3-bar bearish reversal.
    Bar 1: large bullish candle.
    Bar 2: small body (star) that gaps up.
    Bar 3: large bearish candle closing into bar 1's body.
    """
    comp1 = _bar_components(o1, h1, l1, c1)
    comp2 = _bar_components(o2, h2, l2, c2)
    comp3 = _bar_components(o3, h3, l3, c3)

    # Bar 1 must be bullish with a meaningful body
    if not comp1["is_bullish"] or comp1["range"] == 0:
        return None

    body1_ratio = comp1["body"] / comp1["range"]
    if body1_ratio < 0.5:
        return None

    # Bar 2 must have a small body (star)
    star_ratio = comp2["body"] / comp1["range"]
    if star_ratio > 0.3:
        return None

    # Bar 3 must be bearish with a meaningful body
    if not comp3["is_bearish"] or comp3["range"] == 0:
        return None

    body3_ratio = comp3["body"] / comp3["range"]
    if body3_ratio < 0.5:
        return None

    # Bar 3 close should be below midpoint of bar 1's body
    bar1_midpoint = (o1 + c1) / 2.0
    if c3 > bar1_midpoint:
        return None

    strength = min((body1_ratio + body3_ratio) / 2.0, 1.0)
    return {
        "pattern": "evening_star",
        "type": "BEARISH",
        "strength": round(strength, 4),
    }


def detect_all_patterns(df: pd.DataFrame) -> list:
    """
    Scan the most recent bars for all supported candlestick patterns.

    Checks the last 3 bars for: hammer, shooting_star, doji,
    bullish_engulfing, bearish_engulfing, morning_star, evening_star,
    marubozu.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain Open, High, Low, Close columns.

    Returns
    -------
    list[dict]
        Each entry: {pattern: str, type: "BULLISH"/"BEARISH", strength: float 0-1}.
    """
    patterns = []

    if df.empty or len(df) < 1:
        return patterns

    opens = df["Open"].values.astype(float)
    highs = df["High"].values.astype(float)
    lows = df["Low"].values.astype(float)
    closes = df["Close"].values.astype(float)

    n = len(df)

    # --- Single-bar patterns on the last bar ---
    o_last = opens[-1]
    h_last = highs[-1]
    l_last = lows[-1]
    c_last = closes[-1]

    for detector in [_detect_hammer, _detect_shooting_star, _detect_doji, _detect_marubozu]:
        result = detector(o_last, h_last, l_last, c_last)
        if result is not None:
            patterns.append(result)

    # --- Two-bar patterns (last two bars) ---
    if n >= 2:
        o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
        o2, h2, l2, c2 = o_last, h_last, l_last, c_last

        for detector in [_detect_bullish_engulfing, _detect_bearish_engulfing]:
            result = detector(o1, h1, l1, c1, o2, h2, l2, c2)
            if result is not None:
                patterns.append(result)

    # --- Three-bar patterns (last three bars) ---
    if n >= 3:
        o1, h1, l1, c1 = opens[-3], highs[-3], lows[-3], closes[-3]
        o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
        o3, h3, l3, c3 = o_last, h_last, l_last, c_last

        for detector in [_detect_morning_star, _detect_evening_star]:
            result = detector(o1, h1, l1, c1, o2, h2, l2, c2, o3, h3, l3, c3)
            if result is not None:
                patterns.append(result)

    return patterns
