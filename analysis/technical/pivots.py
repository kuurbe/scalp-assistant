"""
Pivot point calculations using all major methods.

Supports Standard (Floor), Woodie, Camarilla, and Fibonacci pivot
methods for identifying intraday support/resistance levels.
"""

import numpy as np


def compute_all_pivots(high: float, low: float, close: float) -> dict:
    """
    Compute pivot points using all four major methods.

    Parameters
    ----------
    high : float
        Previous period high.
    low : float
        Previous period low.
    close : float
        Previous period close.

    Returns
    -------
    dict
        {
            standard: {PP, R1, R2, R3, S1, S2, S3},
            woodie: {PP, R1, R2, R3, S1, S2, S3},
            camarilla: {R1, R2, R3, R4, S1, S2, S3, S4},
            fibonacci: {PP, R1, R2, R3, S1, S2, S3}
        }
    """
    h = float(high)
    l = float(low)
    c = float(close)
    r = h - l  # range

    # ---- Standard (Floor Trader) pivots ----
    pp = (h + l + c) / 3.0
    standard = {
        "PP": round(pp, 6),
        "R1": round(2.0 * pp - l, 6),
        "R2": round(pp + r, 6),
        "R3": round(h + 2.0 * (pp - l), 6),
        "S1": round(2.0 * pp - h, 6),
        "S2": round(pp - r, 6),
        "S3": round(l - 2.0 * (h - pp), 6),
    }

    # ---- Woodie pivots ----
    pp_w = (h + l + 2.0 * c) / 4.0
    woodie = {
        "PP": round(pp_w, 6),
        "R1": round(2.0 * pp_w - l, 6),
        "R2": round(pp_w + r, 6),
        "R3": round(h + 2.0 * (pp_w - l), 6),
        "S1": round(2.0 * pp_w - h, 6),
        "S2": round(pp_w - r, 6),
        "S3": round(l - 2.0 * (h - pp_w), 6),
    }

    # ---- Camarilla pivots ----
    camarilla = {
        "R1": round(c + r * 1.1 / 12.0, 6),
        "R2": round(c + r * 1.1 / 6.0, 6),
        "R3": round(c + r * 1.1 / 4.0, 6),
        "R4": round(c + r * 1.1 / 2.0, 6),
        "S1": round(c - r * 1.1 / 12.0, 6),
        "S2": round(c - r * 1.1 / 6.0, 6),
        "S3": round(c - r * 1.1 / 4.0, 6),
        "S4": round(c - r * 1.1 / 2.0, 6),
    }

    # ---- Fibonacci pivots ----
    pp_f = (h + l + c) / 3.0
    fibonacci = {
        "PP": round(pp_f, 6),
        "R1": round(pp_f + 0.382 * r, 6),
        "R2": round(pp_f + 0.618 * r, 6),
        "R3": round(pp_f + 1.000 * r, 6),
        "S1": round(pp_f - 0.382 * r, 6),
        "S2": round(pp_f - 0.618 * r, 6),
        "S3": round(pp_f - 1.000 * r, 6),
    }

    return {
        "standard": standard,
        "woodie": woodie,
        "camarilla": camarilla,
        "fibonacci": fibonacci,
    }


def get_nearby_pivots(
    price: float,
    pivots: dict,
    tolerance_pct: float = 0.3,
) -> list:
    """
    Find all pivot levels within a percentage tolerance of the current price.

    Parameters
    ----------
    price : float
        Current price.
    pivots : dict
        Output of compute_all_pivots.
    tolerance_pct : float
        Percentage tolerance for proximity (default 0.3%).

    Returns
    -------
    list[dict]
        Each entry: {method, level, label, distance_pct, role}
        where role is "SUPPORT" or "RESISTANCE".
        Sorted by absolute distance ascending.
    """
    if price <= 0:
        return []

    nearby = []
    threshold = tolerance_pct / 100.0

    for method, levels in pivots.items():
        for label, level_value in levels.items():
            if level_value is None or np.isnan(level_value):
                continue

            distance_pct = (level_value - price) / price * 100.0
            abs_distance_ratio = abs(level_value - price) / price

            if abs_distance_ratio <= threshold:
                # Determine role: levels above price are resistance, below are support
                if level_value >= price:
                    role = "RESISTANCE"
                else:
                    role = "SUPPORT"

                nearby.append({
                    "method": method,
                    "level": round(level_value, 6),
                    "label": label,
                    "distance_pct": round(distance_pct, 4),
                    "role": role,
                })

    # Sort by absolute distance
    nearby.sort(key=lambda x: abs(x["distance_pct"]))

    return nearby
