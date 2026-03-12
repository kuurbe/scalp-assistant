"""
Multi-method support/resistance detection with confluence scoring.
Combines: KDE volume profile, fractals, fibonacci, pivots, VWAP bands.
"""
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.stats import gaussian_kde


def kde_support_resistance(df: pd.DataFrame, n_levels: int = 200, bandwidth_pct: float = 0.005) -> list[dict]:
    """
    Gaussian KDE on volume-weighted price levels to find natural S/R.
    Returns list of {price, strength} where strength is normalized 0-1.
    """
    try:
        prices = df["Close"].values
        volumes = df["Volume"].values

        if len(prices) < 10:
            return []

        # Weight prices by volume (repeat each price proportional to volume)
        # Use sampling approach for efficiency
        weights = volumes / volumes.sum()

        p_min, p_max = prices.min(), prices.max()
        price_range = p_max - p_min
        if price_range <= 0:
            return []

        bandwidth = price_range * bandwidth_pct
        grid = np.linspace(p_min, p_max, n_levels)

        # Compute weighted KDE manually (Gaussian kernel)
        density = np.zeros(n_levels)
        for p, w in zip(prices, weights):
            kernel = np.exp(-0.5 * ((grid - p) / bandwidth) ** 2)
            density += w * kernel

        if density.max() > 0:
            density /= density.max()

        # Find peaks in density (strong S/R levels)
        peaks, properties = find_peaks(density, height=0.2, distance=max(3, n_levels // 30))

        levels = []
        for peak_idx in peaks:
            levels.append({
                "price": round(float(grid[peak_idx]), 2),
                "strength": round(float(density[peak_idx]), 3),
                "method": "KDE",
            })

        return sorted(levels, key=lambda x: -x["strength"])[:10]
    except Exception:
        return []


def get_all_levels(ticker: str, daily_df: pd.DataFrame, intraday_df: pd.DataFrame = None) -> dict:
    """
    Compute support/resistance from all available methods and find confluence.
    Returns: {resistance: [...], support: [...], nearest_resistance, nearest_support}
    """
    all_levels = []
    current_price = float(daily_df["Close"].iloc[-1]) if len(daily_df) > 0 else 0

    if current_price <= 0:
        return {"resistance": [], "support": [], "nearest_resistance": None, "nearest_support": None}

    # 1. KDE volume profile
    kde_levels = kde_support_resistance(daily_df)
    all_levels.extend(kde_levels)

    # 2. Williams fractals
    try:
        from analysis.technical.fractals import get_fractal_levels
        df_for_fractals = intraday_df if intraday_df is not None and len(intraday_df) > 10 else daily_df
        fractal_data = get_fractal_levels(df_for_fractals)
        for p in fractal_data.get("resistance", []):
            all_levels.append({"price": round(p, 2), "strength": 0.7, "method": "Fractal"})
        for p in fractal_data.get("support", []):
            all_levels.append({"price": round(p, 2), "strength": 0.7, "method": "Fractal"})
    except Exception:
        pass

    # 3. Fibonacci levels
    try:
        from analysis.technical.fibonacci import detect_swing_points, compute_fibonacci_levels, get_nearby_fib_levels
        swings = detect_swing_points(daily_df)
        if swings.get("swing_high") and swings.get("swing_low"):
            sh = swings["swing_high"][0]
            sl = swings["swing_low"][0]
            fib = compute_fibonacci_levels(sh, sl)
            for ratio, price in fib.get("retracements", []):
                all_levels.append({"price": round(price, 2), "strength": 0.6, "method": f"Fib {ratio}"})
            for ratio, price in fib.get("extensions", []):
                all_levels.append({"price": round(price, 2), "strength": 0.5, "method": f"Fib Ext {ratio}"})
    except Exception:
        pass

    # 4. Pivot points (from prior day)
    try:
        from analysis.technical.pivots import compute_all_pivots
        prev_high = float(daily_df["High"].iloc[-1])
        prev_low = float(daily_df["Low"].iloc[-1])
        prev_close = float(daily_df["Close"].iloc[-1])
        pivots = compute_all_pivots(prev_high, prev_low, prev_close)
        for method_name, levels_dict in pivots.items():
            for label, price in levels_dict.items():
                all_levels.append({"price": round(price, 2), "strength": 0.65, "method": f"{method_name} {label}"})
    except Exception:
        pass

    # 5. VWAP bands (if intraday data available)
    if intraday_df is not None and len(intraday_df) > 10:
        try:
            from analysis.technical.vwap import compute_vwap_bands
            vwap_df = compute_vwap_bands(intraday_df)
            if len(vwap_df) > 0:
                last = vwap_df.iloc[-1]
                for col in ["vwap", "upper_1", "lower_1", "upper_2", "lower_2"]:
                    if col in last and pd.notna(last[col]):
                        all_levels.append({
                            "price": round(float(last[col]), 2),
                            "strength": 0.8 if col == "vwap" else 0.6,
                            "method": f"VWAP {col}",
                        })
        except Exception:
            pass

    # Confluence detection: group nearby levels
    tolerance_pct = 0.003  # 0.3%
    resistance = []
    support = []

    for level in all_levels:
        price = level["price"]
        if price <= 0:
            continue

        if price > current_price:
            # Check confluence with existing resistance levels
            merged = False
            for r in resistance:
                if abs(r["price"] - price) / current_price < tolerance_pct:
                    r["confluence"] += 1
                    r["methods"].append(level["method"])
                    r["strength"] = min(1.0, r["strength"] + 0.1)
                    merged = True
                    break
            if not merged:
                resistance.append({
                    "price": price,
                    "strength": level["strength"],
                    "confluence": 1,
                    "methods": [level["method"]],
                })
        else:
            merged = False
            for s in support:
                if abs(s["price"] - price) / current_price < tolerance_pct:
                    s["confluence"] += 1
                    s["methods"].append(level["method"])
                    s["strength"] = min(1.0, s["strength"] + 0.1)
                    merged = True
                    break
            if not merged:
                support.append({
                    "price": price,
                    "strength": level["strength"],
                    "confluence": 1,
                    "methods": [level["method"]],
                })

    # Sort: resistance ascending (nearest first), support descending (nearest first)
    resistance.sort(key=lambda x: x["price"])
    support.sort(key=lambda x: -x["price"])

    # Filter to meaningful levels (confluence >= 1 and within 10% of price)
    resistance = [r for r in resistance if abs(r["price"] - current_price) / current_price < 0.10][:5]
    support = [s for s in support if abs(s["price"] - current_price) / current_price < 0.10][:5]

    return {
        "resistance": resistance,
        "support": support,
        "nearest_resistance": resistance[0]["price"] if resistance else None,
        "nearest_support": support[0]["price"] if support else None,
    }
